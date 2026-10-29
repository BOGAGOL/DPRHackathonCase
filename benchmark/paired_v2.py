"""Detached-safe official v2 driver: gates, existing paired runner, report and publication."""

import argparse
import ctypes
from datetime import datetime, timezone, timedelta
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
from uuid import UUID

import psycopg

from . import paired
from .ac_monitor import ACMonitor, power_events
from .common import ROOT, file_hash, utc_now, write_json

REQUESTED = '8a11ff7dd39d66317a9802a7224d5ab044210798'
PREFIX = 'bppb_v2'
OUT = ROOT / 'evidence/benchmark'
BRANCH = 'perf/keyservice-latency'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, stderr=subprocess.PIPE).strip()


def production_manifest():
    paths = ['benchmark/adapters/plaintext.py', 'benchmark/adapters/protected.py',
             'benchmark/runner.py', 'benchmark/stats.py', 'benchmark/collect_metrics.py',
             'benchmark/db_time.py', 'benchmark/workloads.yaml', 'migration/model.py',
             'policy/protection_profile.yaml', 'docs/targets.md']
    paths += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / 'toolkit/dprcrypto').glob('*.py'))]
    result = {}
    for path in paths:
        expected = subprocess.check_output(['git', 'show', REQUESTED + ':' + path], cwd=ROOT)
        current = (ROOT / path).read_bytes()
        if expected.replace(b'\r\n', b'\n') != current.replace(b'\r\n', b'\n'):
            raise RuntimeError('production_differs_from_requested_commit')
        result[path] = file_hash(ROOT / path)
    return result


def power_snapshot():
    sample = ACMonitor(ROOT / 'results/bench/bppb_v2/power_gate', OUT).sample()
    events = power_events(sample['timestamp_utc'], sample['timestamp_utc'])
    buffer = ctypes.create_string_buffer(16)
    function = ctypes.WinDLL('powrprof').PowerGetEffectiveOverlayScheme
    function.argtypes, function.restype = [ctypes.c_void_p], ctypes.c_uint
    if function(ctypes.byref(buffer)) != 0:
        raise RuntimeError('power_overlay_unavailable')
    overlay = str(UUID(bytes_le=buffer.raw))
    query = subprocess.check_output(['powercfg', '/query', 'SCHEME_CURRENT', 'SUB_SLEEP', 'STANDBYIDLE'], text=True)
    match = re.search(r'Current AC Power Setting Index:\s*0x([0-9a-fA-F]+)', query)
    sleep = int(match[1], 16) if match else None
    return {'passed': sample['ac_online'] is True
            and events['latest_event_at_or_before_start']['ac_online'] is True
            and overlay == 'ded574b5-45a0-4f42-8737-46345c09c238' and sleep == 0,
            'sample': sample, 'kernel_power': events, 'effective_overlay_guid': overlay,
            'power_mode': 'Best performance' if overlay == 'ded574b5-45a0-4f42-8737-46345c09c238' else 'OTHER',
            'sleep_ac_seconds': sleep}


def members_match(reference, current):
    for db in reference:
        fields = ('rows', 'ciphertext_rows_binary_sha256') if db.startswith('protected') else ('rows', 'checksum_sha256', 'sequence')
        if any(reference[db][k] != current[db][k] for k in fields):
            return False
    return True


def preflight():
    report = {'started_at_utc': utc_now(), 'passed': False, 'official_runs_started': False,
              'requested_production_commit': REQUESTED, 'gates': {}}
    def require(name, passed, **details):
        report['gates'][name] = {'passed': bool(passed), **details}
        if not passed:
            raise RuntimeError('gate_' + name)
    try:
        require('branch', git('branch', '--show-current') == BRANCH)
        require('commit_ancestor', subprocess.run(['git', 'merge-base', '--is-ancestor', REQUESTED, 'HEAD'], cwd=ROOT).returncode == 0,
                commit=REQUESTED, committed_at_wib=git('show', '-s', '--format=%cI', REQUESTED))
        hashes = production_manifest()
        require('production', True, sha256=hashes, transport='https_pool', dek_cache_ttl_seconds=0)
        require('runtime_config', os.environ.get('DPR_OPENBAO_HTTP_TRANSPORT') == 'https_pool'
                and os.environ.get('DPR_BENCH_DEK_CACHE_TTL') == '0')
        target = subprocess.check_output(['git', 'show', paired.TARGET + ':docs/targets.md'], cwd=ROOT)
        require('target', subprocess.run(['git', 'merge-base', '--is-ancestor', paired.TARGET, 'HEAD'], cwd=ROOT).returncode == 0
                and target.replace(b'\r\n', b'\n') == (ROOT / 'docs/targets.md').read_bytes().replace(b'\r\n', b'\n'),
                commit=paired.TARGET, committed_at_wib=git('show', '-s', '--format=%cI', paired.TARGET),
                before_first_run=True)
        report['gates']['power'] = power_snapshot()
        if not report['gates']['power']['passed']:
            raise RuntimeError('gate_power')
        paired.services()
        require('services', True, running_containers=paired.CONTAINERS, openbao_unsealed=True)
        token_gate = paired.ensure_token(minimum_ttl_seconds=10800)
        require('benchmark_token', True, **token_gate)
        with psycopg.connect(**paired.admin_parameters('baseline_100k'), autocommit=True) as admin:
            others = admin.execute("SELECT usename,application_name,state,count(*) FROM pg_stat_activity "
                "WHERE backend_type='client backend' AND pid<>pg_backend_pid() AND datname=ANY(%s) "
                "GROUP BY usename,application_name,state", (['postgres','baseline_100k','baseline_1m','protected_100k','protected_1m'],)).fetchall()
            require('workload_sessions', not others, other_sessions=sum(r[3] for r in others))
            settings = admin.execute("SELECT current_setting('shared_preload_libraries'),current_setting('server_version')").fetchone()
            require('pg_stat_statements_preload', 'pg_stat_statements' in settings[0], preload=settings[0], postgres=settings[1])
        for db in ('baseline_100k','baseline_1m','protected_100k','protected_1m'):
            with psycopg.connect(**paired.admin_parameters(db), autocommit=True) as admin:
                require('extension_' + db, admin.execute("SELECT to_regclass('public.pg_stat_statements') IS NOT NULL").fetchone()[0])
        naive = json.loads((OUT / 'bppb_session.json').read_text())
        require('naive_preserved', naive['status'] == 'COMPLETED' and naive['variant'] == 'naive_v1')
        corpora = {}
        for scale in paired.SCALES:
            path = Path(os.environ['DPR_PRIVATE_DIR']) / 'benchmark' / f'baseline_{scale}_keys_v1.json'
            require('key_corpus_' + scale, path.is_file() and file_hash(path) == naive['scales'][scale]['key_corpus']['sha256'])
            corpora[scale] = naive['scales'][scale]['key_corpus']
        require('workload_unchanged', subprocess.check_output(['git','show',naive['code_commit']+':benchmark/workloads.yaml'],cwd=ROOT).replace(b'\r\n',b'\n')
                == (ROOT/'benchmark/workloads.yaml').read_bytes().replace(b'\r\n',b'\n'))
        report['key_corpora'] = corpora
        parity = json.loads((OUT / 'keyservice_latency/https_pool_v2/parity_cache_0.json').read_text())
        require('parity', parity['passed'] and parity['dek_cache_ttl_seconds'] == 0
                and all(file_hash(ROOT/p) == value for p,value in parity['production_files_sha256'].items()))
        reference = json.loads((OUT / 'keyservice_latency/https_pool_v2/integrity.json').read_text())['after']
        report['databases'] = paired.integrity()
        require('integrity', members_match(reference, report['databases']), reference='keyservice_latency/https_pool_v2/integrity.json')
        require('disk', shutil.disk_usage(ROOT).free >= 20*1024**3, free_bytes=shutil.disk_usage(ROOT).free, minimum_bytes=20*1024**3)
        report['environment'] = {'os':platform.platform(),'python':platform.python_version(),
            'dependencies':{name:importlib.metadata.version(name) for name in ('psycopg','psutil','httpx','cryptography','PyYAML')}}
        report['orchestration_commit'] = git('rev-parse','HEAD')
        report['passed'] = True
    except Exception as error:
        report.update(error_type=type(error).__name__, error='preflight_failed_private_details_withheld')
        if isinstance(error, RuntimeError) and str(error).startswith('benchmark_token_'):
            report['gates']['benchmark_token'] = {'passed':False, 'reason':str(error),
                'minimum_ttl_seconds':10800, 'automatic_issuance':False}
        if isinstance(error, RuntimeError) and str(error) in (
                'container_set_changed', 'openbao_unavailable_or_sealed', 'disk_under_20_GiB'):
            report['gates']['services'] = {'passed':False, 'reason':str(error)}
    finally:
        report['completed_at_utc'] = utc_now()
        write_json(OUT / (PREFIX + '_preflight.json'), report)
    return report


def versions_summary():
    lines = ['# B-P-P-B DB: naive_v1 dan v2', '',
        'Median antar empat run per mode/skenario. V2: https_pool, DEK cache OFF; target tidak berubah.',
        'Plain disajikan terpisah untuk setiap sesi. Rasio/delta dan target memakai plain dalam sesi yang sama;',
        'perubahan antarsesi menggambarkan hasil dua sesi terpisah, bukan pasangan run simultan.', '',
        '| Skala | Skenario | Sesi | Mode | p50 ms | p95 ms | req/s | error % | db_time ms/req | Delta p95 ms | Rasio p95 | P01 | P01A | P02 | P03 |',
        '|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|---|']
    comparisons = {name:json.loads((OUT/path).read_text()) for name,path in
                   [('naive_v1','bppb_compare.json'),('v2','bppb_v2_compare.json')]}
    status = lambda value: 'LULUS' if value else 'GAGAL'
    for scale in paired.SCALES:
        for version, report in comparisons.items():
            for row in report['scales'][scale]:
                for mode, metrics in [('plain',row['before']),('protected',row['after'])]:
                    tail = ['0.000','1.000','ACUAN','ACUAN','ACUAN','ACUAN'] if mode == 'plain' else [
                        f"{row['p95_delta_ms']:.3f}", f"{row['p95_ratio']:.3f}", status(row['P01_ratio_passed']),
                        status(row['P01_absolute_passed']),status(row['P02_passed']),status(row['P03_passed'])]
                    cells = [scale,row['scenario'],version,mode,f"{metrics['p50_ms']:.3f}",f"{metrics['p95_ms']:.3f}",
                        f"{metrics['throughput_rps']:.2f}",f"{100*metrics['error_rate']:.6f}",f"{metrics['db_time_ms_per_request']:.4f}",*tail]
                    lines.append('| '+' | '.join(cells)+' |')
    session = json.loads((OUT/'bppb_v2_session.json').read_text())
    invalid = sum(a['status'] != 'VALID' for s in session['scales'].values() for a in s['attempts'])
    errors = sum(r['errors'] for s in session['scales'].values() for r in s['rows'])
    lines += ['',f'V2 status: {session["status"]}; integritas akhir: {session.get("datasets_unchanged")}; '
              f'error terukur: {errors}; blok invalid/disimpan: {invalid}.',
              'Semua raw gzip dan metadata berada di direktori masing-masing versi. Tidak menghapus run buruk.',
              'db_time adalah mean SQL execution/request, bukan percentile server; non-DB tetap tersedia dalam JSON.']
    destination = OUT / 'bppb_versions_summary.md'
    destination.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return destination


def publish(session):
    """Publish only this session's paths, without checkout/merge or other staged work."""
    if git('branch','--show-current') != BRANCH:
        raise RuntimeError('publication_branch_changed')
    paths = [f'evidence/benchmark/{PREFIX}_preflight.json', f'evidence/benchmark/{PREFIX}_session.json',
             f'evidence/benchmark/{PREFIX}_launch.json', 'benchmark/NOTES.md']
    paths += [str(p.relative_to(ROOT)).replace('\\','/') for p in
              [OUT/'bppb_v2_100k',OUT/'bppb_v2_1m',OUT/'bppb_v2_compare.json',OUT/'bppb_versions_summary.md'] if p.exists()]
    paths = [p for p in paths if (ROOT/p).exists()]
    subprocess.run(['git','add','--',*paths],cwd=ROOT,check=True,capture_output=True)
    subprocess.run(['git','commit','--only','-m','evidence: official B-P-P-B v2 https_pool cache off ('+session['status']+')','--',*paths],
                   cwd=ROOT,check=True,capture_output=True)
    receipt = {'commit':git('rev-parse','HEAD'),'committed_at_wib':git('show','-s','--format=%cI','HEAD'),
               'status':'COMMITTED','branch':BRANCH}
    write_json(ROOT/'results/bench/bppb_v2/publication.json',receipt)
    subprocess.run(['git','push','origin','HEAD:refs/heads/'+BRANCH],cwd=ROOT,check=True,capture_output=True)
    receipt.update(status='PUSHED',completed_at_utc=utc_now())
    write_json(ROOT/'results/bench/bppb_v2/publication.json',receipt)
    return receipt


def run():
    raw = ROOT/'results/bench/bppb_v2'
    raw.mkdir(parents=True,exist_ok=True)
    with (raw/'worker.lock').open('x') as handle:
        handle.write(str(os.getpid()))
    session = {'status':'STOPPED','error':'initial_gate_or_execution_failed'}
    try:
        gate = json.loads((OUT/'bppb_v2_preflight.json').read_text())
        if not gate['passed'] or (datetime.now(timezone.utc)-datetime.fromisoformat(gate['completed_at_utc'])).total_seconds()>600:
            raise RuntimeError('preflight_missing_failed_or_stale')
        hashes = production_manifest()
        if os.environ.get('DPR_OPENBAO_HTTP_TRANSPORT') != 'https_pool' or os.environ.get('DPR_BENCH_DEK_CACHE_TTL') != '0':
            raise RuntimeError('runtime_configuration_changed')
        if not power_snapshot()['passed']:
            raise RuntimeError('power_gate_changed')
        token_gate = paired.ensure_token(minimum_ttl_seconds=10800)
        metadata = {'variant':'v2','requested_production_commit':REQUESTED,'production_file_sha256':hashes,
            'initial_token_gate':token_gate,'minimum_progress_check_interval_seconds':1200,
            'orchestration_commit':git('rev-parse','HEAD'),'orchestration_file_sha256':{
                p:file_hash(ROOT/p) for p in ('benchmark/paired.py','benchmark/paired_v2.py','benchmark/start_bppb_v2.ps1')},
            'http_transport':'https_pool','dek_cache_ttl_seconds':0,'worker_pid':os.getpid(),
            'started_at_wib':datetime.now(timezone(timedelta(hours=7))).isoformat(),
            'detached':True,'logs':'results/bench/bppb_v2/runner.stdout.log and runner.stderr.log'}
        session = paired.execute(prefix=PREFIX,metadata=metadata)
        if session['status']=='COMPLETED':
            versions_summary()
    except Exception as error:
        session.update(status='STOPPED',error_type=type(error).__name__,error='v2_driver_stopped_private_details_withheld')
        write_json(OUT/'bppb_v2_session.json',session)
    with (ROOT/'benchmark/NOTES.md').open('a',encoding='utf-8') as handle:
        handle.write('\n\n## B-P-P-B resmi v2 — hasil worker terpisah\n\nStatus '+session['status']+
            '; produksi8a11ff7, https_pool, DEK cache OFF. Gate, count/checksum lima DB, resource dan AC per run disimpan di evidence/benchmark/bppb_v2_*. '
            'Metode/run sama dengan naive_v1; hanya direktori/metadata dan publikasi otomatis ditambahkan pada orchestration. '
            'Seluruh hasil naive_v1 dipertahankan. Tabel lengkap: evidence/benchmark/bppb_versions_summary.md. '
            'Integritas akhir: '+str(session.get('datasets_unchanged','BELUM LENGKAP'))+'. Tidak merge ke main.\n')
    try:
        receipt = publish(session)
        print(json.dumps({'status':session['status'],'publication':receipt}),flush=True)
    except Exception as error:
        write_json(raw/'publication_failure.json',{'error_type':type(error).__name__,'at_utc':utc_now(),
            'details_withheld':True,'automatic_retry':False})
        raise SystemExit('Publication failed; local results retained') from None
    return session


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['preflight','run'])
    args = parser.parse_args()
    result = preflight() if args.action=='preflight' else run()
    print(json.dumps({'status':result.get('status'),'preflight_passed':result.get('passed')}),flush=True)
    raise SystemExit(0 if result.get('passed') or result.get('status')=='COMPLETED' else 1)


if __name__=='__main__':
    main()
