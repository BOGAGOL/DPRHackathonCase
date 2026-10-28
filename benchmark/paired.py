"""Official paired DB session. No migrations, restarts, unseal or dataset maintenance."""

from collections import Counter
from datetime import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import threading
import time
from uuid import uuid4

import psutil
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
import yaml

from datagen.model import COLUMNS, checksum
from infra.openbao.api import from_environment
from infra.openbao.init import save_response
from .ac_monitor import ACMonitor, power_events, qualify
from .adapters.plaintext import PlaintextAdapter, load_keys
from .adapters.protected import ProtectedAdapter
from .collect_metrics import Collector
from .common import ROOT, utc_now, write_json, write_csv, file_hash, running_containers
from .compare import compare_metrics
from .db_time import DbTimeMonitor, monitoring_parameters
from .parity import prepare_scope, remove_scope
from .runner import one_run
from .stats import medians

CONTAINERS = ['dpr-infra-openbao-1', 'pg-dpr']
SCALES = {'100k': 100000, '1m': 1000000}
TARGET = '8c09a25ccb6d415a231f692b68b9674495c31faf'


def admin_parameters(database, writable=False):
    if database not in {'postgres', 'baseline_100k', 'baseline_1m', 'protected_100k', 'protected_1m'}:
        raise ValueError('Unauthorized dataset')
    p = monitoring_parameters()
    p.update(dbname=database, application_name='dpr-paired-monitor',
             options='-c default_transaction_read_only=' + ('off' if writable else 'on'))
    return p


def services():
    if running_containers() != CONTAINERS:
        raise RuntimeError('container_set_changed')
    state = from_environment().request('/sys/seal-status')
    if not state['initialized'] or state['sealed']:
        raise RuntimeError('openbao_unavailable_or_sealed')
    if shutil.disk_usage(ROOT).free < 20 * 1024**3:
        raise RuntimeError('disk_under_20_GiB')


def ensure_token():
    """Operator-only issuance. Root is never installed in the workload environment."""
    api = from_environment()
    token = os.environ.get('OPENBAO_TOKEN')
    ttl = 0
    if token:
        try:
            info = api.request('/auth/token/lookup-self', token=token)['data']
            if info['policies'] != ['svc-app']:
                raise ValueError('Unexpected token policy')
            ttl = info['ttl']
        except Exception:
            ttl = 0
    issued = False
    if ttl < 5400:
        private = Path(os.environ['DPR_SECRETS_DIR']) / 'openbao'
        root = json.loads((private / 'init-material.json').read_text())['root_token']
        destination = private / 'tokens' / ('svc-app-bppb-' + datetime.now().strftime('%Y%m%dT%H%M%S') + '-' + uuid4().hex[:8] + '.json')
        response = save_response(destination, lambda: api.request('/auth/token/create-orphan',
            {'policies': ['svc-app'], 'no_default_policy': True, 'renewable': False,
             'ttl': '14400s', 'explicit_max_ttl': '14400s', 'display_name': 'dpr-bppb-svc-app'}, token=root))
        del root
        os.environ['OPENBAO_TOKEN'] = response['auth']['client_token']
        ttl = api.request('/auth/token/lookup-self', token=os.environ['OPENBAO_TOKEN'])['data']['ttl']
        issued = True
    return {'policy': 'svc-app', 'ttl_seconds': ttl, 'new_4h_token_issued': issued, 'at_utc': utc_now()}


def integrity():
    """Canonical plaintext checksums; deterministic binary COPY hash for ciphertext rows."""
    result = {}
    for db, expected_rows in [('postgres', 734), ('baseline_100k', 100000), ('baseline_1m', 1000000),
                               ('protected_100k', 100000), ('protected_1m', 1000000)]:
        protected = db.startswith('protected')
        table = 'anggota_protected' if protected else 'anggota'
        with psycopg.connect(**admin_parameters(db), row_factory=dict_row) as c:
            c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            n = c.execute(sql.SQL('SELECT count(*) AS n FROM public.{}').format(sql.Identifier(table))).fetchone()['n']
            if n != expected_rows:
                raise ValueError('Dataset count mismatch')
            record = {'rows': n, 'rows_match': True}
            if protected:
                h = hashlib.sha256()
                with c.cursor() as cur:
                    with cur.copy('COPY (SELECT * FROM public.anggota_protected ORDER BY legacy_row_id) TO STDOUT (FORMAT BINARY)') as stream:
                        for block in stream:
                            h.update(block)
                record['ciphertext_rows_binary_sha256'] = h.hexdigest()
                record['control_counts'] = {t: c.execute(sql.SQL('SELECT count(*) AS n FROM public.{}').format(sql.Identifier(t))).fetchone()['n']
                                           for t in ('app_users', 'access_scope', 'audit_log')}
            else:
                with c.cursor(name='bppb_integrity') as cur:
                    cur.execute(sql.SQL('SELECT {} FROM public.anggota ORDER BY id').format(sql.SQL(',').join(map(sql.Identifier, COLUMNS))))
                    digest = checksum(cur)
                record['checksum_sha256'] = digest
                doc = json.loads((ROOT / 'evidence/datasets' / ('baseline_100k.json' if db == 'postgres' else db + '.json')).read_text())
                expected = doc['validation']['source_checksum_sha256'] if db == 'postgres' else doc['baseline_checksum_sha256']
                if digest != expected:
                    raise ValueError('Canonical dataset checksum mismatch')
                record['sequence'] = c.execute('SELECT last_value,is_called FROM public.anggota_id_seq').fetchone()
            record['database_bytes'] = c.execute('SELECT pg_database_size(current_database()) AS n').fetchone()['n']
            result[db] = record
    return result


def unchanged(before, after):
    for db in before:
        fields = ['rows', 'ciphertext_rows_binary_sha256'] if db.startswith('protected') else ['rows', 'checksum_sha256', 'sequence']
        if any(before[db][k] != after[db][k] for k in fields):
            return False
        if db.startswith('protected') and any(before[db]['control_counts'][t] != after[db]['control_counts'][t] for t in ('app_users', 'access_scope')):
            return False
    return True


class RunGuard:
    def __init__(self, power):
        self.power, self.stop = power, threading.Event()
        self.ended = threading.Event()
        self.reason = None
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self.watch, daemon=True)
        self.thread.start()

    def watch(self):
        tick = 0
        while not self.ended.is_set():
            if self.power.collection_failure:
                self.reason = 'ac_collection_failed'
            elif any(s['ac_online'] is not True for s in self.power.samples):
                self.reason = 'ac_interrupted'
            elif tick % 5 == 0:
                try:
                    services()
                except Exception:
                    self.reason = 'services_or_disk_gate_failed'
            if self.reason:
                self.stop.set()
                return
            tick += 1
            self.ended.wait(1)

    def finish(self):
        self.ended.set()
        if self.thread:
            self.thread.join(timeout=15)
        if self.thread and self.thread.is_alive():
            self.reason = 'runtime_guard_did_not_stop'
        return self.reason


def compress_run(directory):
    manifest = []
    for source in sorted(directory.glob('*.csv')):
        digest = file_hash(source)
        target = source.with_suffix(source.suffix + '.gz')
        with source.open('rb') as incoming, gzip.open(target, 'xb', compresslevel=1) as outgoing:
            shutil.copyfileobj(incoming, outgoing)
        h = hashlib.sha256()
        with gzip.open(target, 'rb') as stream:
            for block in iter(lambda: stream.read(1024*1024), b''):
                h.update(block)
        if h.hexdigest() != digest:
            raise ValueError('Compressed raw hash mismatch')
        manifest.append({'file': target.name, 'uncompressed_sha256': digest, 'compressed_sha256': file_hash(target),
                         'uncompressed_bytes': source.stat().st_size, 'compressed_bytes': target.stat().st_size})
        source.unlink()
    write_json(directory / 'raw_manifest.json', manifest)
    return manifest


def run_once(adapter, mode, database, scenario, ordinal, manifest, directory, power):
    services()
    power.require_ac()
    started = utc_now()
    guard = RunGuard(power)
    monitor = DbTimeMonitor(database, 'bench_user' if mode == 'B' else 'app_user')
    guard.start()
    try:
        result = one_run(adapter, scenario, ordinal, manifest, 8, 60, 10, directory,
                         db_monitor=monitor, stop_event=guard.stop, reset_statistics=True,
                         collector_factory=lambda path: Collector(path, containers=CONTAINERS))
    except Exception:
        guard.finish()
        if guard.reason == 'ac_interrupted':
            return {'interrupted': True, 'reason': guard.reason, 'scenario': scenario, 'mode': mode}
        raise
    finally:
        guard.finish()
        monitor.close()
    if guard.reason and guard.reason != 'ac_interrupted':
        raise RuntimeError('Service/disk/monitor failure; stop session')
    events = power_events(started, utc_now())
    samples = [s for s in power.samples if s['timestamp_utc'] >= started]
    ac = qualify(samples, events)
    result.update(mode=mode, adapter='plain' if mode == 'B' else 'protected', database=database,
                  ac=ac, free_disk_bytes=shutil.disk_usage(ROOT).free, valid=ac['qualified'] and not guard.reason,
                  client_non_db_mean_ms=result['mean_ms'] - result['db_time']['db_time_ms_per_request'],
                  non_db_definition='mean client end-to-end minus mean SQL execution; includes planning/network/crypto/validation/rollback; not percentile subtraction')
    with psycopg.connect(**admin_parameters(database), autocommit=True) as c:
        result['database_bytes'] = c.execute('SELECT pg_database_size(current_database())').fetchone()[0]
    write_json(directory / 'summary.json', result)
    write_json(directory / 'power_events.json', events)
    compress_run(directory)
    return result


def aggregate(rows):
    report = []
    for mode in ('B', 'P'):
        for scenario in dict.fromkeys(r['scenario'] for r in rows):
            group = [r for r in rows if r['mode'] == mode and r['scenario'] == scenario and r.get('valid')]
            if len(group) != 4:
                raise ValueError('Expected four valid runs per mode/scenario')
            values = {'mode': mode, 'scenario': scenario, 'runs': 4, **medians(group)}
            values['db_time_ms_per_request'] = statistics.median(r['db_time']['db_time_ms_per_request'] for r in group)
            values['non_db_mean_ms'] = statistics.median(r['client_non_db_mean_ms'] for r in group)
            values['requests_total'] = sum(r['requests'] for r in group)
            values['errors_total'] = sum(r['errors'] for r in group)
            values['warmup_errors_total'] = sum(r['warmup_errors'] for r in group)
            report.append(values)
    return report


def comparison(summaries):
    result = {'level': 'DB', 'api_status': 'BELUM DIUJI', 'scales': {}, 'targets_commit': TARGET,
              'ratio_and_absolute_reported_separately': True, 'old_threshold_definition': 'P01 AND P02 AND P03; absolute allowance does not replace the ratio',
              'non_db_definition': 'median per-run (mean client latency minus mean pg_stat_statements execution); not p50/p95 subtraction'}
    for scale, rows in summaries.items():
        entries = []
        for scenario in dict.fromkeys(r['scenario'] for r in rows):
            b = next(r for r in rows if r['mode'] == 'B' and r['scenario'] == scenario)
            p = next(r for r in rows if r['mode'] == 'P' and r['scenario'] == scenario)
            if b['p95_ms'] <= 0 or b['throughput_rps'] <= 0:
                entries.append({'scenario':scenario,'before':b,'after':p,'status':'TIDAK DAPAT DINILAI',
                                'reason':'baseline denominator zero or invalid; no favorable substitution'})
                continue
            c = compare_metrics(b, p, scenario)
            c.update(before=b, after=p,
                     old_threshold_all_passed=c['P01_ratio_passed'] and c['P02_passed'] and c['P03_passed'],
                     absolute_with_P02_P03_passed=c['P01_absolute_passed'] and c['P02_passed'] and c['P03_passed'],
                     all_current_targets_passed=c['P01_ratio_passed'] and c['P01_absolute_passed'] and c['P02_passed'] and c['P03_passed'])
            entries.append(c)
        result['scales'][scale] = entries
    return result


def invalidate_block(info, folder):
    info['status'] = 'TERDAMPAK_BATERAI'
    for r in info['runs']:
        r.update(valid=False, environment_label='terdampak baterai; seluruh blok dikecualikan')
        if r.get('raw'):
            path = ROOT / r['raw'] / 'summary.json'
            if path.exists():
                write_json(path, r)
    write_json(folder / 'BLOCK_INVALID_BATTERY.json', {'status':info['status'], 'block':info['block'],
        'attempt':info['attempt'], 'excluded_runs':len(info['runs']), 'repeat':'whole B-P-P-B block'})


def execute(prefix='bppb', metadata=None):
    """Two whole B/P/P/B blocks per scale; an AC incident invalidates all 28 runs."""
    out = ROOT / 'evidence/benchmark'
    if prefix not in ('bppb', 'bppb_v2'):
        raise ValueError('Unauthorized session prefix')
    session_file = out / (prefix + '_session.json')
    preflight = json.loads((out / (prefix + '_preflight.json')).read_text())
    if not preflight['passed']:
        raise ValueError('Initial gate failed')
    if session_file.exists() or any((out / (prefix + '_' + s) / 'session.json').exists() for s in SCALES):
        raise ValueError('Existing paired session; refusing automatic overwrite/resume')
    manifest = yaml.safe_load((ROOT / 'benchmark/workloads.yaml').read_text())
    session = {'status': 'RUNNING', 'started_at_utc': utc_now(), 'target_commit': TARGET,
               'code_commit': subprocess.run(['git','rev-parse','HEAD'], capture_output=True,text=True,check=True).stdout.strip(),
               'parameters': {'concurrency':8,'duration_s':60,'warmup_s':10,'blocks':2,'order':['B','P','P','B']},
               'control_audit_note':'Temporary RLS setup/cleanup is retained in append-only audit_log; member rows and business sequences must be identical. No workload write commits.',
               'scales': {}, 'variant_metadata': metadata or {}}
    write_json(session_file, session)
    summaries = {}
    try:
        services()
        session['initial_integrity'] = integrity()
        for scale in SCALES:
            services()
            base, protected = 'baseline_' + scale, 'protected_' + scale
            keys, corpus = load_keys(manifest, 8, base)
            destination = out / (prefix + '_' + scale)
            rows, attempts, principal = [], [], None
            with psycopg.connect(**admin_parameters(protected, True), autocommit=True) as admin:
                principal, authorized = prepare_scope(admin, keys)
                try:
                    os.environ['DPR_BENCH_PRINCIPAL'] = principal
                    adapters = {'B':PlaintextAdapter(keys,base), 'P':ProtectedAdapter(keys,protected)}
                    session['scales'][scale] = {'key_corpus':corpus,'authorized_records':authorized,'attempts':attempts,'rows':rows,
                                               'variant_metadata':metadata or {}}
                    for block in (1,2):
                        attempt = 0
                        while True:
                            attempt += 1
                            services()
                            token = ensure_token()
                            folder = destination / f'block_{block}' / f'attempt_{attempt}'
                            power = ACMonitor(folder / 'power_raw', folder)
                            power.start()
                            current = []
                            info = {'block':block,'attempt':attempt,'status':'RUNNING','token':token,'runs':current}
                            attempts.append(info)
                            try:
                                for phase,mode in enumerate(('B','P','P','B'),1):
                                    for scenario in manifest['scenarios']:
                                        ordinal = (block-1)*2 + (1 if phase in (1,2) else 2)
                                        directory = folder / f'{phase}_{mode}' / scenario
                                        print(json.dumps({'phase':'starting','scale':scale,'block':block,'attempt':attempt,'mode':mode,'scenario':scenario,'at_utc':utc_now()}),flush=True)
                                        r = run_once(adapters[mode],mode,base if mode=='B' else protected,scenario,ordinal,manifest,directory,power)
                                        r.update(block=block,attempt=attempt,phase=phase,raw=directory.relative_to(ROOT).as_posix())
                                        current.append(r)
                                        write_json(destination / 'session.json',session['scales'][scale])
                                        write_json(session_file,session)
                                        print(json.dumps({'phase':'finished','scale':scale,'block':block,'mode':mode,'scenario':scenario,'p95_ms':r.get('p95_ms'),'throughput_rps':r.get('throughput_rps'),'errors':r.get('errors'),'valid':r.get('valid')}),flush=True)
                                        if r.get('interrupted') or not r.get('valid'):
                                            raise InterruptedError('AC interrupted; invalidate whole block')
                            except InterruptedError:
                                invalidate_block(info,folder)
                            finally:
                                ac = power.finish()
                                info['power'] = ac
                            if not ac['qualified']:
                                invalidate_block(info,folder)
                            if info['status']=='TERDAMPAK_BATERAI':
                                write_json(destination/'session.json',session['scales'][scale])
                                print(json.dumps({'phase':'waiting_ac','scale':scale,'block':block,'discarded_runs':len(current)}),flush=True)
                                while not (psutil.sensors_battery() and psutil.sensors_battery().power_plugged):
                                    services();time.sleep(2)
                                continue
                            info['status']='VALID'
                            rows.extend(current)
                            break
                    summaries[scale]=aggregate(rows)
                    flat=[{k:v for k,v in r.items() if not isinstance(v,(dict,list))} for r in rows]
                    write_csv(destination/'summary.csv',flat)
                    write_csv(destination/'per_mode.csv',summaries[scale])
                    write_json(destination/'summary.json',{'median_between_runs':summaries[scale],'all_runs':rows,
                                                          'variant_metadata':metadata or {}})
                finally:
                    remove_scope(admin,principal)
                    os.environ.pop('DPR_BENCH_PRINCIPAL',None)
            write_json(destination/'session.json',session['scales'][scale])
        session['final_integrity']=integrity()
        session['datasets_unchanged']=unchanged(session['initial_integrity'],session['final_integrity'])
        if not session['datasets_unchanged']:
            raise ValueError('Final dataset checksum/sequence mismatch')
        report=comparison(summaries)
        report.update(completed_at_utc=utc_now(),datasets_unchanged=True,variant_metadata=metadata or {})
        write_json(out/(prefix+'_compare.json'),report)
        session['status']='COMPLETED'
    except Exception as error:
        session.update(status='STOPPED',error_type=type(error).__name__,error='paired_session_stopped_details_withheld')
        print(json.dumps({'status':'STOPPED','error_type':type(error).__name__}),flush=True)
    finally:
        session['completed_at_utc']=utc_now()
        session['free_disk_bytes']=shutil.disk_usage(ROOT).free
        write_json(session_file,session)
    return session


if __name__=='__main__':
    result=execute()
    print(json.dumps({'status':result['status'],'free_disk_bytes':result['free_disk_bytes']}),flush=True)
    raise SystemExit(0 if result['status']=='COMPLETED' else 1)
