"""Detached API experiment, with OID guarded cleanup even after worker failure."""
import argparse
from collections import Counter
from datetime import datetime, timezone, timedelta
import gzip
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import random
import shutil
import statistics
import subprocess
import sys
import threading
import time
from urllib.parse import quote, urlencode

import httpx
import psutil
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from benchmark import paired, paired_v2
from benchmark.ac_monitor import ACMonitor
from benchmark.collect_metrics import docker_sample
from benchmark.common import ROOT, file_hash, running_containers, utc_now, write_json, write_csv
from benchmark.stats import summarize, medians
from infra.openbao.api import from_environment
from infra.security import secure_directory
from .client import BASE, ENDPOINTS, client, login, request, mismatched_fields
from .db_swap import PGStore, Swap

OUT = ROOT / 'evidence/benchmark/api_bppb_100k'
JOURNAL = OUT / 'db_swap_state.json'
RAW = ROOT / 'results/bench/api_bppb_100k'
APP_PYTHON = ROOT / 'app/.venv/Scripts/python.exe'
K6 = Path('C:/Program Files/k6/k6.exe')
CA = Path('C:/dev/dpr-private/openbao/tls/ca.crt')
PORT = 8100
BLOCK_COUNT = 1
RUNS_PER_MODE = 2 * BLOCK_COUNT
DESIGN_CHANGE = {
    'authorized_on_wib_date': '2026-10-29',
    'reason': 'Operator time limit; explicitly reduced from two B-P-P-B blocks to one before measurement.',
    'previous_blocks': 2, 'blocks': BLOCK_COUNT,
    'previous_runs_per_mode_per_endpoint': 4, 'runs_per_mode_per_endpoint': RUNS_PER_MODE,
    'median_over_runs': RUNS_PER_MODE, 'total_runs': BLOCK_COUNT * 4 * len(ENDPOINTS),
    'targets_changed': False,
    'limitation': 'Two repetitions per mode are below the original three-run minimum; reduced API evidence must be reported with this limitation.'
}


def production_hashes():
    paths = list((ROOT/'app/backend/service_app').glob('*.py')) + list((ROOT/'app/scripts').glob('*.py'))
    paths += list((ROOT/'toolkit/dprcrypto').glob('*.py')) + list((ROOT/'benchmark/api').glob('*.py'))
    paths += [ROOT/'benchmark/api/load.js', ROOT/'docs/targets.md', ROOT/'policy/protection_profile.yaml']
    return {p.relative_to(ROOT).as_posix(): file_hash(p) for p in sorted(paths)}


def service_url(database, admin=False):
    p = conninfo_to_dict(os.environ['BENCH_MONITOR_DATABASE_URL' if admin else 'PROTECTED_DATABASE_URL'])
    return ('postgresql+psycopg://' + quote(p['user'], safe='') + ':' + quote(p['password'], safe='')
            + '@127.0.0.1:5433/' + database + '?' + urlencode({'sslmode':'verify-full', 'sslrootcert':p['sslrootcert']}))


def application_env(mode):
    # Do not pass admin/monitoring/bench credentials to the HTTP service.
    env = {k:v for k,v in os.environ.items() if k.upper() in
           {'SYSTEMROOT','WINDIR','PATH','TEMP','TMP','USERPROFILE','LOCALAPPDATA','APPDATA','COMSPEC'}}
    env.update(MODE=mode, DATABASE_URL=service_url('baseline_100k' if mode=='plain' else 'protected_100k'),
               APP_ORIGIN=BASE, SESSION_TTL_SECONDS='900', API_PORT=str(PORT),
               TLS_CERT_FILE=str(CA.parent/'server.crt'), TLS_KEY_FILE=str(CA.parent/'server.key'),
               PYTHONPATH=os.pathsep.join((str(ROOT/'toolkit'),str(ROOT))), PYTHONDONTWRITEBYTECODE='1',
               DPR_OPENBAO_HTTP_TRANSPORT='https_pool', DPR_BENCH_DEK_CACHE_TTL='0')
    if mode == 'protected':
        env.update({k:os.environ[k] for k in ('OPENBAO_ADDR','OPENBAO_CACERT','OPENBAO_TOKEN')})
    return env


def official_snapshot():
    data = paired.integrity()
    # Also fingerprint all small control tables and sequences; member data is above.
    for db in data:
        with psycopg.connect(**paired.admin_parameters(db), autocommit=True) as c:
            tables = [r[0] for r in c.execute("SELECT relname FROM pg_class WHERE relnamespace='public'::regnamespace "
                      "AND relkind='r' AND relname NOT IN ('anggota','anggota_protected') ORDER BY relname")]
            controls = {}
            for name in tables:
                digest = hashlib.sha256()
                with c.cursor().copy(sql.SQL('COPY (SELECT * FROM public.{} ORDER BY ctid) TO STDOUT (FORMAT BINARY)').format(sql.Identifier(name))) as stream:
                    for block in stream: digest.update(block)
                controls[name] = {'sha256':digest.hexdigest(), 'rows':c.execute(sql.SQL('SELECT count(*) FROM public.{}').format(sql.Identifier(name))).fetchone()[0]}
            data[db]['all_control_tables'] = controls
            data[db]['all_sequences'] = [list(row) for row in c.execute("SELECT schemaname,sequencename,last_value FROM pg_sequences WHERE schemaname='public' ORDER BY sequencename")]
    return data


def services():
    if running_containers() != paired.CONTAINERS:
        raise RuntimeError('api_service_container_changed')
    s = from_environment().request('/sys/seal-status')
    if s['sealed'] or not s['initialized']:
        raise RuntimeError('api_openbao_sealed_or_unavailable')
    if shutil.disk_usage(ROOT).free < 10*1024**3:
        raise RuntimeError('api_disk_under_10_GiB')


def preflight():
    record = {'started_at_utc':utc_now(), 'passed':False, 'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()}
    try:
        if subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip() != 'perf/keyservice-latency':
            raise RuntimeError('wrong_branch')
        record['power'] = paired_v2.power_snapshot()
        if not record['power']['passed']:raise RuntimeError('api_power_gate_failed')
        services()
        record['token'] = paired.ensure_token(7200)
        # One block including login cooldowns fits within the unchanged two-hour gate.
        record['session_token_budget'] = paired.ensure_token(7200)
        record['design_change'] = DESIGN_CHANGE
        record['before'] = official_snapshot()
        reference = json.loads((ROOT/'evidence/benchmark/bppb_v2_session.json').read_text())['final_integrity']
        if not paired_v2.members_match(reference, record['before']):raise RuntimeError('official_data_changed')
        if any(x.laddr.port==PORT and x.status=='LISTEN' for x in psutil.net_connections(kind='tcp') if x.laddr):
            raise RuntimeError('api_port_already_occupied')
        record.update(passed=True, production_sha256=production_hashes(), disk_free_bytes=shutil.disk_usage(ROOT).free)
    except Exception as error:
        record.update(error_type=type(error).__name__, error='preflight_failed_details_withheld')
    write_json(OUT/'active_preflight.json', record)
    return record


def guarded_command(args, env):
    write_json(OUT/'setup_progress.json',{'script':Path(args[1]).name,'mode':env['MODE'],'status':'RUNNING','at_utc':utc_now()})
    completed = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, timeout=240)
    write_json(OUT/'setup_progress.json',{'script':Path(args[1]).name,'mode':env['MODE'],
        'status':'PASS' if completed.returncode==0 else 'FAIL','exit_code':completed.returncode,'at_utc':utc_now()})
    if completed.returncode:raise RuntimeError('official_setup_command_failed_details_withheld')


def grant_copy_prerequisites(swap, database):
    """Connection/schema grants are prerequisites omitted by B's table-only CLI."""
    expected=swap.state['copies'].get(database)
    if (swap.state['status']!='swapped' or not expected
            or expected in {v['oid'] for v in swap.state['originals'].values()}
            or swap.store.entries().get(database,{}).get('oid')!=expected):
        raise RuntimeError('copy_grant_target_not_owned_copy')
    with psycopg.connect(**paired.admin_parameters(database,True)) as c:
        actual=c.execute('SELECT oid FROM pg_database WHERE datname=current_database()').fetchone()[0]
        if actual!=expected:raise RuntimeError('copy_connection_oid_mismatch')
        c.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO app_user').format(sql.Identifier(database)))
        c.execute('GRANT USAGE ON SCHEMA public TO app_user')


def prepare(private, swap):
    source = Path(os.environ['DPR_PRIVATE_DIR'])/'benchmark/baseline_100k_keys_v1.json'
    original = json.loads(source.read_text(encoding='utf-8'))
    profiles = [{k:r[k] for k in ('id','no_ktp','email')} for r in original['profiles']]
    random.Random(42).shuffle(profiles)
    keys = {'profiles':profiles, 'pages':[p['anchor']//50+1 for p in original['pages']]}
    key_path = private/'keys.json'; key_path.write_text(json.dumps(keys),encoding='utf-8')
    accounts = {}
    for mode, db in [('plain','baseline_100k'),('protected','protected_100k')]:
        grant_copy_prerequisites(swap,db)
        env = application_env(mode)
        env['APP_SETUP_DATABASE_URL'] = service_url(db, True)
        env['DPR_PRIVATE_DIR'] = str(secure_directory(private/mode))
        env['DEMO_MEMBER_PRINCIPAL'] = original['profiles'][0]['pengguna']
        env['DEMO_ASSIGNED_IDS'] = ','.join(str(r['id']) for r in original['profiles'][:100])
        guarded_command([str(APP_PYTHON),'app/scripts/schema.py','--database',db],env)
        guarded_command([str(APP_PYTHON),'app/scripts/provision.py'],env)
        accounts[mode] = Path(env['DPR_PRIVATE_DIR'])/'service-b'/f'service-b-{mode}-accounts.json'
        if mode == 'protected':
            account = next(a for a in json.loads(accounts[mode].read_text()) if a['role']=='privileged_officer')
            with psycopg.connect(**paired.admin_parameters(db,True)) as c:
                identifier = c.execute('SELECT user_id FROM app_users WHERE username=%s',(account['username'],)).fetchone()[0]
                c.execute("INSERT INTO access_scope(principal,anggota_id,permission,source_label) "
                          "SELECT %s,anggota_id,'read','manual' FROM anggota_protected ON CONFLICT DO NOTHING",(identifier,))
                n = c.execute("SELECT count(*) FROM access_scope WHERE principal=%s AND permission='read'",(identifier,)).fetchone()[0]
                if n != 100000:raise RuntimeError('api_scope_not_full_population')
    app_versions=json.loads(subprocess.check_output([str(APP_PYTHON),'-c',
        "import importlib.metadata as m,json;print(json.dumps({n:m.version(n) for n in ['fastapi','uvicorn','starlette','pydantic','SQLAlchemy','psycopg','cryptography','httpx']}))"],text=True))
    write_json(OUT/'setup.json',{'passed':True,'official_cli':True,'demo_accounts_per_mode':6,'benchmark_accounts_used_per_mode':1,
        'role':'privileged_officer','protected_read_scope_rows':100000,'scope_reason':'Full population required for list total/page parity with plain; includes entire fixed DB key pool.',
        'key_profiles':len(profiles),'pages':len(keys['pages']),'seed':42,'source_corpus_sha256':file_hash(source),
        'db_tls_both_modes':'verify-full','app_versions':app_versions,
        'client':{n:importlib.metadata.version(n) for n in ('httpx','psutil')},'at_utc':utc_now()})
    return keys, key_path, accounts


def stop_owned_app(identity):
    """Windows venv launcher is not the server: stop owned children before parent."""
    if not identity:return
    records=list(identity.get('children',[]))
    if psutil.pid_exists(identity['pid']):
        parent=psutil.Process(identity['pid'])
        if parent.create_time()!=identity['created']:raise RuntimeError('api_parent_pid_reused')
        records += [{'pid':p.pid,'created':p.create_time()} for p in parent.children(recursive=True)]
    records.append({'pid':identity['pid'],'created':identity['created']})
    stopped=[];seen=set()
    for record in records:
        if record['pid'] in seen or not psutil.pid_exists(record['pid']):continue
        seen.add(record['pid']);p=psutil.Process(record['pid'])
        if p.create_time()!=record['created'] or not any('serve.py' in a for a in p.cmdline()):
            raise RuntimeError('api_process_identity_mismatch')
        p.terminate();stopped.append(p)
    _,alive=psutil.wait_procs(stopped,timeout=10)
    for p in alive:p.kill()
    _,alive=psutil.wait_procs(alive,timeout=5)
    if alive:raise RuntimeError('api_process_failed_to_stop')
    if any(x.laddr.port==PORT and x.status=='LISTEN' for x in psutil.net_connections(kind='tcp') if x.laddr):
        raise RuntimeError('api_port_still_listening_refuse_name_restore')


class App:
    def __init__(self, swap, private):
        self.swap,self.private,self.proc,self.mode,self.handles,self.last_login = swap,private,None,None,[],None

    def start(self, mode):
        if self.proc and self.mode==mode:return False
        self.stop()
        name = 'baseline_100k' if mode=='plain' else 'protected_100k'
        if self.swap.state['status']!='swapped' or self.swap.store.entries()[name]['oid']!=self.swap.state['copies'][name]:
            raise RuntimeError('app_target_not_owned_copy')
        stamp=str(time.time_ns())
        self.handles=[(self.private/(stamp+s)).open('wb') for s in ('.stdout.log','.stderr.log')]
        self.proc=subprocess.Popen([str(APP_PYTHON),'app/scripts/serve.py'],cwd=ROOT,env=application_env(mode),
            stdout=self.handles[0],stderr=self.handles[1],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.swap.state['app']={'pid':self.proc.pid,'created':psutil.Process(self.proc.pid).create_time()}
        self.swap.save('swapped');self.mode=mode;self.last_login=None
        with client(CA) as s:
            for _ in range(60):
                if self.proc.poll() is not None:raise RuntimeError('api_app_start_failed_private_logs_retained')
                try:
                    if s.get('/health/ready').status_code==200:
                        children=psutil.Process(self.proc.pid).children(recursive=True)
                        self.worker_pid=children[-1].pid if children else self.proc.pid
                        self.swap.state['app']['children']=[{'pid':p.pid,'created':p.create_time()} for p in children]
                        self.swap.state['app']['server_pid']=self.worker_pid
                        self.swap.save('swapped')
                        return True
                except httpx.HTTPError:pass
                time.sleep(1)
        raise RuntimeError('api_app_readiness_timeout')

    def stop(self):
        if self.swap.state is not None:stop_owned_app(self.swap.state.get('app'))
        if self.proc:self.proc.wait(timeout=10)
        self.proc=None;self.mode=None
        for h in self.handles:h.close()
        self.handles=[]
        if self.swap.state is not None and self.swap.state.get('app'):
            self.swap.state['app']=None
            self.swap.save(self.swap.state['status'])


def parity(app, keys, accounts):
    before={};bad=[];count=0
    for mode in ('plain','protected'):
        app.start(mode)
        with client(CA) as s:
            account=next(a for a in json.loads(accounts[mode].read_text()) if a['role']=='privileged_officer')
            login(s,account)
            for i,key in enumerate(keys['profiles'][:200]):
                for endpoint in ENDPOINTS:
                    response=request(s,endpoint,key,keys['pages'][i%len(keys['pages'])])
                    if response.status_code!=200:raise RuntimeError('parity_http_status_'+str(response.status_code))
                    if mode=='plain':before[i,endpoint]=response.json()
                    else:
                        differences=mismatched_fields(before.pop((i,endpoint)),response.json())
                        if differences:bad.append({'endpoint':endpoint,'field_names':differences[:10]})
                        count+=1
        app.stop()
    report={'passed':not bad,'samples_per_endpoint':200,'comparisons':count,'http_requests':count*2,'mismatches':bad,
            'ignored':'headers/request_id only; all JSON body fields compared','at_utc':utc_now()}
    write_json(OUT/'parity.json',report)
    if bad:raise RuntimeError('api_parity_mismatch')
    return report


class Resources:
    def __init__(self,path,app_pid,client_pid):
        self.path,self.app_pid,self.client_pid=path,app_pid,client_pid
        self.rows=[];self.stop=threading.Event();self.thread=None

    def start(self):
        self.thread=threading.Thread(target=self.collect,daemon=True);self.thread.start()

    def collect(self):
        app,load=psutil.Process(self.app_pid),psutil.Process(self.client_pid)
        app.cpu_percent(None);load.cpu_percent(None)
        while not self.stop.is_set():
            row={'timestamp_utc':utc_now(),'ok':True}
            try:
                row.update(docker_sample(paired.CONTAINERS),app_cpu_percent_one_core=app.cpu_percent(None),app_rss_bytes=app.memory_info().rss,
                           client_cpu_percent_one_core=load.cpu_percent(None),client_rss_bytes=load.memory_info().rss)
            except Exception:row['ok']=False
            self.rows.append(row);self.stop.wait(2)

    def finish(self):
        self.stop.set();self.thread.join(timeout=15)
        write_json(self.path,self.rows)
        return summarize_resources(self.rows)


def summarize_resources(rows, started=None, completed=None):
    """Keep measurement CPU/RSS separate from login and warmup samples."""
    if started is not None:
        first=datetime.fromisoformat(started.replace('Z','+00:00'))
        last=datetime.fromisoformat(completed.replace('Z','+00:00'))
        rows=[r for r in rows if first<=datetime.fromisoformat(r['timestamp_utc'].replace('Z','+00:00'))<=last]
    good=[r for r in rows if r['ok']]
    fields=set().union(*(r.keys() for r in good))-{'timestamp_utc','ok'} if good else set()
    return {'samples':len(rows),'failed_samples':len(rows)-len(good),
            **{f+'_median':statistics.median(r[f] for r in good) for f in fields},
            **{f+'_peak':max(r[f] for r in good) for f in fields}}


def parse_raw(path):
    latencies=[];errors=0;statuses=Counter();starts=[];ends=[]
    with path.open(encoding='utf-8') as handle:
        for line in handle:
            p=json.loads(line)
            if p.get('type')!='Point' or p.get('metric')!='api_latency_ms':continue
            data=p['data'];latencies.append(data['value']);errors+=data['tags']['ok']!='1';statuses[data['tags']['status']]+=1
            end=datetime.fromisoformat(data['time'].replace('Z','+00:00')).timestamp()
            starts.append(end-data['value']/1000);ends.append(end)
    elapsed=max(60,max(ends)-min(starts)) if latencies else 60
    return {**summarize(latencies,errors,elapsed),'http_status_counts':dict(statuses),
            'latency_definition':'k6 response.timings.blocked + duration; full response, no login/warmup samples',
            'measurement_started_at_utc':datetime.fromtimestamp(min(starts),timezone.utc).isoformat(),
            'measurement_completed_at_utc':datetime.fromtimestamp(max(ends),timezone.utc).isoformat()}


def run_once(app, endpoint, directory, key_path, account_path, warmup, power, hashes):
    if production_hashes()!=hashes:raise RuntimeError('api_production_changed_requires_new_session')
    services();paired.ensure_token(300)
    if app.last_login is not None:
        deadline=app.last_login+310
        while time.monotonic()<deadline:
            power.require_ac()
            if app.proc.poll() is not None:raise RuntimeError('api_app_crashed')
            services();time.sleep(min(5,max(.01,deadline-time.monotonic())))
    directory.mkdir(parents=True,exist_ok=False)
    raw=directory/'k6.json'
    env={k:v for k,v in os.environ.items() if k.upper() in
         {'SYSTEMROOT','WINDIR','PATH','TEMP','TMP','USERPROFILE','LOCALAPPDATA','APPDATA','COMSPEC'}}
    env.update({'API_KEYS_FILE':str(key_path),'API_ACCOUNT_FILE':str(account_path),'API_ENDPOINT':endpoint,
         'API_WARMUP_SECONDS':str(warmup),'K6_NO_USAGE_REPORT':'true','K6_NO_COLOR':'true'}
    )
    proc=subprocess.Popen([str(K6),'run','--quiet','--include-system-env-vars','--log-output=none','--out','json='+str(raw),str(ROOT/'benchmark/api/load.js')],
                          cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    resources=Resources(directory/'resources.json',app.worker_pid,proc.pid);resources.start()
    try:
        while proc.poll() is None:
            power.require_ac()
            if app.proc.poll() is not None:raise RuntimeError('api_app_crashed')
            services();time.sleep(2)
        app.last_login=time.monotonic()-60-warmup # conservative setup-end plus 310s interval
        if proc.returncode:raise RuntimeError('api_k6_failed_no_private_output_logged')
    finally:
        if proc.poll() is None:proc.terminate();proc.wait(timeout=15)
        summary_resources=resources.finish()
    result=parse_raw(raw)
    result.update(endpoint=endpoint,mode=app.mode,warmup_seconds=warmup,
        resources=summarize_resources(resources.rows,result['measurement_started_at_utc'],result['measurement_completed_at_utc']),
        resources_including_setup=summary_resources,ac_confirmed=True)
    for p in (raw,directory/'resources.json'):
        with p.open('rb') as source,gzip.open(str(p)+'.gz','wb',compresslevel=1) as target:shutil.copyfileobj(source,target)
        p.unlink()
    write_json(directory/'summary.json',result)
    return result


def compare(rows):
    result=[]
    for endpoint in ENDPOINTS:
        b=[r for r in rows if r['mode']=='plain' and r['endpoint']==endpoint and r['valid']]
        p=[r for r in rows if r['mode']=='protected' and r['endpoint']==endpoint and r['valid']]
        if len(b)!=RUNS_PER_MODE or len(p)!=RUNS_PER_MODE:raise RuntimeError('api_two_runs_per_mode_required')
        before,after=medians(b),medians(p)
        ratio=after['p95_ms']/before['p95_ms'] if before['p95_ms'] else None
        throughput=after['throughput_rps']/before['throughput_rps'] if before['throughput_rps'] else None
        result.append({'endpoint':endpoint,'before':before,'after':after,'p95_delta_ms':after['p95_ms']-before['p95_ms'],
            'p95_ratio':ratio,'throughput_ratio':throughput,'P01_ratio_passed':ratio is not None and ratio<=1.5,
            'P01_absolute_passed':after['p95_ms']<=before['p95_ms']+5,'P02_passed':throughput is not None and throughput>=.7,
            'P03_passed':after['error_rate']<=before['error_rate']})
    return {'status':'COMPLETED','level':'API','scale':'100k','target_commit':paired.TARGET,
            'design_change':DESIGN_CHANGE,'scenarios':result,
            'scope':'GET read paths only; write/mixed API targets remain untested','db_comparison':'Side by side only; API DB TLS both modes, HTTPS/FastAPI/auth/audit/DTO differ from direct DB v2.'}


def verify_restored(swap, before):
    after=official_snapshot()
    if not paired_v2.members_match(before,after):raise RuntimeError('api_final_member_integrity_mismatch')
    for db in before:
        if before[db]['all_control_tables']!=after[db]['all_control_tables'] or before[db]['all_sequences']!=after[db]['all_sequences']:
            raise RuntimeError('api_final_official_control_or_sequence_changed')
    checks=[]
    for env in ('BENCH_DATABASE_URL','SCANNER_DATABASE_URL'):
        for db in ('baseline_100k','baseline_1m'):
            params=conninfo_to_dict(os.environ[env]);params.update(dbname=db,sslmode='disable',options='-c default_transaction_read_only=on')
            with psycopg.connect(**params) as c:
                n=c.execute('SELECT count(*) FROM public.anggota').fetchone()[0]
                tls=c.execute('SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()').fetchone()[0]
                if tls or n!=before[db]['rows']:raise RuntimeError('baseline_nossl_exception_failed')
                checks.append({'role':params['user'],'database':db,'rows':n,'ssl':tls,'passed':True})
    swap.state['verification']={'passed':True,'before':before,'after':after,'baseline_nossl':checks,'at_utc':utc_now()}
    swap.save('restored')
    write_json(OUT/'final_integrity.json',swap.state['verification'])


def publish(report):
    if subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()!='perf/keyservice-latency':
        raise RuntimeError('api_publication_branch_changed')
    with (ROOT/'evidence/benchmark/run-notes.md').open('a',encoding='utf-8') as h:
        h.write('\n\n## API B-P-P-B 100k — '+utc_now()+'\n\nStatus '+report['status']+
            '. Clone bernama baseline_100k/protected_100k karena allowlist app; originals diarsip sementara __official dan dilindungi OID/ALLOW_CONNECTIONS. '
            'Journal db_swap_state.json wajib restored setelah count/checksum/control/sequence/TLS bench+scanner lolos. '
            'App asli tanpa edit, TLS verify-full kedua mode, 8VU/60s, warmup30s per start, cooldown login310s agar satu akun tidak kena limiter10/5menit. '
            'Raw/summary/parity/metadata di evidence/benchmark/api_bppb_100k. Tidak mengganti hasil DB.\n')
    if report['status']=='COMPLETED':
        comparison=json.loads((ROOT/'evidence/benchmark/api_bppb_compare.json').read_text())
        with (ROOT/'evidence/benchmark/bppb_versions_summary.md').open('a',encoding='utf-8') as h:
            h.write('\n\n### Level API — hasil 100k, satu blok atas batas waktu operator\n\nTLS DB kedua mode, HTTPS/FastAPI/auth/audit ikut terukur; DTO berbeda dari DB. Median dua run per mode (satu B-P-P-B); di bawah minimum awal tiga pengulangan. Target tidak diubah.\n\n'
                    '| Endpoint | p50 B/P ms | p95 B/P ms | req/s B/P | Rasio p95 | P01/P01A/P02/P03 |\n|---|---:|---:|---:|---:|---|\n')
            for r in comparison['scenarios']:
                b,p=r['before'],r['after'];statuses='/'.join('LULUS' if r[k] else 'GAGAL' for k in ('P01_ratio_passed','P01_absolute_passed','P02_passed','P03_passed'))
                h.write(f"| {r['endpoint']} | {b['p50_ms']:.3f}/{p['p50_ms']:.3f} | {b['p95_ms']:.3f}/{p['p95_ms']:.3f} | {b['throughput_rps']:.2f}/{p['throughput_rps']:.2f} | {r['p95_ratio']:.3f} | {statuses} |\n")
    paths=['evidence/benchmark/run-notes.md','evidence/benchmark/api_bppb_100k','evidence/benchmark/bppb_versions_summary.md']
    if (ROOT/'evidence/benchmark/api_bppb_compare.json').exists():paths.append('evidence/benchmark/api_bppb_compare.json')
    subprocess.run(['git','add','--',*paths],cwd=ROOT,check=True,capture_output=True)
    subprocess.run(['git','commit','--only','-m','evidence: API read-path B-P-P-B ('+report['status']+')','--',*paths],cwd=ROOT,check=True,capture_output=True)
    subprocess.run(['git','push','origin','HEAD:refs/heads/perf/keyservice-latency'],cwd=ROOT,check=True,capture_output=True)
    write_json(RAW/'publication.json',{'status':'PUSHED','commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'at_utc':utc_now()})


def run():
    RAW.mkdir(parents=True,exist_ok=True)
    if JOURNAL.exists():raise RuntimeError('existing_swap_journal_do_not_overwrite')
    gate=preflight()
    if not gate['passed']:return {'status':'STOPPED_INITIAL_GATE'}
    write_json(OUT/'official_before.json',gate['before'])
    private=secure_directory(Path(os.environ['DPR_PRIVATE_DIR'])/'benchmark'/('api_'+str(time.time_ns())))
    store=PGStore();swap=Swap(store,JOURNAL);app=App(swap,private)
    report={'status':'RUNNING','code_commit':gate['code_commit'],'production_sha256':gate['production_sha256'],
        'started_at_utc':utc_now(),'rows':[],'attempts':[],'design_change':DESIGN_CHANGE,
        'parameters':{'vus':8,'duration_seconds':60,'warmup_after_start_seconds':30,'blocks':BLOCK_COUNT,'order':['B','P','P','B'],
        'login_cooldown_seconds':310,'why_cooldown':'one account, 8 logins/run, limiter 10 per 300s'},
        'tool':subprocess.check_output([str(K6),'version'],text=True).strip(),'app_python':str(APP_PYTHON.relative_to(ROOT)),
        'database_transport_both_modes':'app_user verify-full same CA','dek_cache':'OFF','http_transport':'https_pool',
        'environment':{'os':platform.platform(),'cpu':platform.processor(),'logical_cores':psutil.cpu_count(),
                       'ram_bytes':psutil.virtual_memory().total,'controller_python':platform.python_version()},
        'watchdog':'Separate supervisor restores unfinished swap after worker exit; restore_failed requires operator, no automatic retry.'}
    write_json(OUT/'session.json',report)
    try:
        swap.swap()
        report['stage']='prepare_clones'
        keys,key_path,accounts=prepare(private,swap)
        report['stage']='parity'
        report['parity']=parity(app,keys,accounts)
        report['stage']='measurement'
        for block in range(1,BLOCK_COUNT+1):
            attempt=0
            while True:
                attempt+=1;directory=OUT/f'block_{block}'/f'attempt_{attempt}'
                power=ACMonitor(directory/'power_raw',directory);power.start()
                current=[];info={'block':block,'attempt':attempt,'status':'RUNNING','runs':current};report['attempts'].append(info)
                try:
                    for phase,mode in enumerate(('plain','protected','protected','plain'),1):
                        restarted=app.start(mode)
                        for i,endpoint in enumerate(ENDPOINTS):
                            print(json.dumps({'phase':'starting','block':block,'attempt':attempt,'mode':mode,'endpoint':endpoint,'at_utc':utc_now()}),flush=True)
                            row=run_once(app,endpoint,directory/f'{phase}_{mode}'/endpoint,key_path,accounts[mode],30 if restarted and i==0 else 0,power,gate['production_sha256'])
                            row.update(valid=True,block=block,phase=phase,attempt=attempt,
                                       raw=(directory/f'{phase}_{mode}'/endpoint).relative_to(ROOT).as_posix());current.append(row)
                            write_json(ROOT/row['raw']/'summary.json',row)
                            write_json(OUT/'session.json',report)
                            print(json.dumps({'phase':'finished','mode':mode,'endpoint':endpoint,'errors':row['errors'],'p95_ms':row['p95_ms']}),flush=True)
                except ValueError:
                    if not any(s['ac_online'] is False for s in power.samples):raise
                    info['status']='TERDAMPAK_BATERAI'
                finally:
                    info['power']=power.finish()
                if not info['power']['qualified']:
                    info['status']='TERDAMPAK_BATERAI'
                if info['status']=='TERDAMPAK_BATERAI':
                    for r in current:
                        r['valid']=False
                        write_json(ROOT/r['raw']/'summary.json',r)
                    write_json(directory/'BLOCK_INVALID_BATTERY.json',{'status':'TERDAMPAK_BATERAI','repeat':'whole B-P-P-B block','discarded_runs':len(current)})
                    app.stop();write_json(OUT/'session.json',report)
                    while not (psutil.sensors_battery() and psutil.sensors_battery().power_plugged):services();time.sleep(5)
                    continue
                info['status']='VALID';report['rows'].extend(current);break
        app.stop()
        write_json(ROOT/'evidence/benchmark/api_bppb_compare.json',compare(report['rows']))
        write_csv(OUT/'summary.csv',[{k:v for k,v in row.items() if not isinstance(v,(dict,list))} for row in report['rows']])
        report['status']='COMPLETED'
    except BaseException as error:
        report.update(status='STOPPED',error_type=type(error).__name__,error='api_experiment_failed_private_details_withheld')
    finally:
        try:
            app.stop()
            swap.restore()
            if swap.state is not None:verify_restored(swap,gate['before'])
        except BaseException as error:
            report.update(status='RESTORE_FAILED',restore_error_type=type(error).__name__)
            if swap.state is not None:swap.save('restore_failed')
        store.close()
        report['completed_at_utc']=utc_now();write_json(OUT/'session.json',report)
        publish(report)
    return report


def recover():
    store=PGStore();swap=Swap(store,JOURNAL)
    try:
        if swap.state and swap.state['status']!='restored':
            stop_owned_app(swap.state.get('app'))
            swap.restore()
            verify_restored(swap,json.loads((OUT/'official_before.json').read_text()))
    except BaseException:
        if swap.state is not None:swap.save('restore_failed')
        raise
    finally:store.close()


def supervise():
    try:
        subprocess.run([sys.executable,'-m','benchmark.api','run'],cwd=ROOT,check=False)
    finally:
        if JOURNAL.exists():
            status=json.loads(JOURNAL.read_text())['status']
            if status=='restore_failed':raise RuntimeError('api_restore_failed_operator_action_required')
            if status!='restored':recover()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['preflight','run','recover','supervise'])
    action=parser.parse_args().action
    if action=='preflight':print(json.dumps({'passed':preflight()['passed']}))
    elif action=='recover':recover()
    elif action=='supervise':supervise()
    else:print(json.dumps({'status':run()['status']}),flush=True)
