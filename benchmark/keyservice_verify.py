"""Nonofficial post-change correctness/leak/smoke verification, with cache-off variant."""

import argparse
import json
import os
from pathlib import Path

import psycopg
import yaml

from .ac_monitor import ACMonitor
from .adapters.plaintext import PlaintextAdapter, load_keys
from .adapters.protected import ProtectedAdapter
from .collect_metrics import Collector
from .common import ROOT, utc_now, write_json, file_hash
from .db_time import DbTimeMonitor
from .paired import CONTAINERS, admin_parameters, compress_run, services
from .parity import prepare_scope, remove_scope, run as parity_run
from .runner import one_run
from .stats import medians


BASE = ROOT / 'evidence/benchmark/keyservice_latency'


def verify_parity():
    reports = []
    for ttl in (0, 60):
        os.environ['DPR_BENCH_DEK_CACHE_TTL'] = str(ttl)
        report = parity_run(BASE / f'parity_cache_{ttl}.json', samples=1000)
        reports.append(report)
        print(json.dumps({'phase': 'parity', 'ttl_seconds': ttl, 'passed': report['passed']}), flush=True)
        if not report['passed']:
            raise RuntimeError('Parity gate failed')
    return reports


def verify_leak():
    # No production token is read by protected_dump_no_key; reuse the real immutable dump.
    from verify.protected_artifact import measure, protected_rows
    from verify.artifacts import expand_dump
    from verify.known_values import KnownValues
    from verify.leakage_budget import ratio
    from uuid import uuid4
    report = {'started_at_utc': utc_now(), 'passed': False, 'datasets': []}
    for scale in ('100k', '1m'):
        private = Path(os.environ['DPR_PRIVATE_DIR']) / 'verify'
        artifact = private / 'after_20261028' / f'protected_{scale}.dump'
        expected = json.loads((ROOT / 'evidence/overnight/after_artifacts_20261028.json').read_text())
        fingerprint = file_hash(artifact)
        if fingerprint != expected['stages'][f'protected_{scale}']['sha256']:
            raise RuntimeError('Immutable dump fingerprint changed')
        expanded = artifact.parent / ('perf-no-key-' + uuid4().hex + '.sql')
        profile = yaml.safe_load((ROOT / 'policy/protection_profile.yaml').read_text())
        known = KnownValues(private / f'baseline_{scale}_known.sqlite')
        try:
            expand_dump(artifact, expanded)
            populations, _, _, _ = measure(protected_rows(expanded, profile), known, profile,
                                           'protected_dump_no_key', None)
            all_rows = populations['all']
            score = ratio(sum(all_rows['exposed_cells'].values()), sum(known.meta['non_null_cells']['all'].values()))
            passed = score['numerator'] == 0
            result = {'database': f'protected_{scale}', 'passed': passed, 'ESCE': score,
                      'artifact_sha256': fingerprint, 'rows_checked': all_rows['rows'],
                      'crypto_client_constructed': False, 'storage_format_changed': False,
                      'scope': 'Existing actual protected dump; historical evidence retained',
                      'timestamp_utc': utc_now()}
            write_json(BASE / f'no_key_{scale}.json', result)
        finally:
            known.close()
            if expanded.exists():
                expanded.unlink()
        report['datasets'].append({'database': f'protected_{scale}', 'passed': passed,
                                  'ESCE': score, 'artifact_sha256': fingerprint})
        if not passed:
            raise RuntimeError('No-key exposure gate failed')
    report.update(passed=True, completed_at_utc=utc_now())
    write_json(BASE / 'no_key_gate.json', report)
    return report


def smoke():
    """Two 30-second runs per variant; never label as official or evaluate targets."""
    services()
    for name in ('parity_cache_0.json', 'parity_cache_60.json', 'no_key_gate.json'):
        if not json.loads((BASE / name).read_text()).get('passed'):
            raise RuntimeError('Verification gate missing or failed')
    from infra.openbao.api import from_environment
    identity = from_environment().request('/auth/token/lookup-self', token=os.environ['OPENBAO_TOKEN'])['data']
    if identity['policies'] != ['svc-app']:
        raise RuntimeError('Unexpected smoke identity')
    token_info = {'ttl_seconds': identity['ttl'], 'new_4h_token_issued': False}
    if identity['ttl'] < 900:
        from .paired import ensure_token
        token_info = ensure_token()
    from dprcrypto import BlindIndexer, OpenBaoClient
    with OpenBaoClient() as client:
        indexer = BlindIndexer(client)
        inputs = [('no_ktp', '00000000000001'), ('email', ' SYNTHETIC@EXAMPLE.COM '),
                  ('pengguna', ' SyntheticCase ')]
        batch = indexer.digests(inputs)
        if batch != [indexer.digest(column, value) for column, value in inputs]:
            raise RuntimeError('Live HMAC batch equivalence failed')
        write_json(BASE / 'hmac_batch_parity.json', {'passed': True, 'synthetic_inputs': True,
            'columns_compared': 3, 'batch_rpc_count': 1, 'serial_rpc_count': 3,
            'values_exported': False, 'timestamp_utc': utc_now()})
    manifest = yaml.safe_load((ROOT / 'benchmark/workloads.yaml').read_text())
    keys, corpus = load_keys(manifest, 8, 'baseline_100k')
    report = {'kind': 'nonofficial_smoke', 'started_at_utc': utc_now(), 'passed': False,
              'http_transport': os.environ.get('DPR_OPENBAO_HTTP_TRANSPORT', 'https_pool'),
              'workload_token': token_info,
              'duration_s': 30, 'warmup_s': 10, 'concurrency': 8,
              'scenario': 'read_by_nik', 'key_corpus': corpus, 'runs': [],
              'cache_caveat': '2048 fixed profiles; temporal reuse can inflate cache benefit versus larger/changing keys',
              'order': ['plain', 'protected_cache_off', 'protected_cache_60',
                        'protected_cache_60', 'protected_cache_off', 'plain']}
    with psycopg.connect(**admin_parameters('protected_100k', writable=True), autocommit=True) as admin:
        principal, _ = prepare_scope(admin, keys)
        previous = os.environ.get('DPR_BENCH_PRINCIPAL')
        os.environ['DPR_BENCH_PRINCIPAL'] = principal
        power_dir = ROOT / 'results/bench' / ('keyservice_smoke_power_' + BASE.name)
        power_dir.mkdir(parents=True, exist_ok=False)
        power = ACMonitor(power_dir, BASE)
        power_started = False
        try:
            power.start()
            power_started = True
            for index, variant in enumerate(report['order'], 1):
                services()
                if any(s['ac_online'] is not True for s in power.samples):
                    raise RuntimeError('AC interrupted; nonofficial smoke stopped')
                plain = variant == 'plain'
                os.environ['DPR_BENCH_DEK_CACHE_TTL'] = '60' if variant.endswith('_60') else '0'
                adapter = PlaintextAdapter(keys) if plain else ProtectedAdapter(keys)
                directory = ROOT / 'results/bench' / ('keyservice_smoke_' + BASE.name) / f'{index}_{variant}'
                monitor = DbTimeMonitor('baseline_100k' if plain else 'protected_100k',
                                        'bench_user' if plain else 'app_user')
                try:
                    result = one_run(adapter, 'read_by_nik', index, manifest, 8, 30, 10,
                        directory, db_monitor=monitor, collector_factory=lambda path:
                        Collector(path, containers=CONTAINERS))
                finally:
                    monitor.close()
                result['variant'] = variant
                result['official'] = False
                report['runs'].append(result)
                write_json(directory / 'summary.json', result)
                compress_run(directory)
                write_json(BASE / 'smoke.json', report)
                print(json.dumps({'phase': 'smoke', 'variant': variant, 'run': index,
                                  'p95_ms': result['p95_ms'], 'errors': result['errors']}), flush=True)
                if result['errors'] or result['warmup_errors']:
                    raise RuntimeError('Smoke correctness error')
            report['medians'] = {variant: medians([r for r in report['runs'] if r['variant'] == variant])
                                 for variant in set(report['order'])}
            report.update(passed=True, completed_at_utc=utc_now())
        finally:
            try:
                if power_started:
                    report['power_verification'] = power.finish()
                    if not report['power_verification']['qualified']:
                        report['passed'] = False
            finally:
                report['power_samples'] = power.samples
                remove_scope(admin, principal)
                if previous is None:
                    os.environ.pop('DPR_BENCH_PRINCIPAL', None)
                else:
                    os.environ['DPR_BENCH_PRINCIPAL'] = previous
                write_json(BASE / 'smoke.json', report)
    if not report['passed']:
        raise RuntimeError('Smoke verification failed')
    return report


def main():
    global BASE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['parity', 'leak', 'smoke'])
    parser.add_argument('--session', choices=['https_pool_v2'])
    args = parser.parse_args()
    if args.session:
        BASE = BASE / args.session
    BASE.mkdir(parents=True, exist_ok=True)
    functions = {'parity': verify_parity, 'leak': verify_leak, 'smoke': smoke}
    try:
        functions[args.phase]()
    except Exception as error:
        write_json(BASE / (args.phase + '_failure.json'), {'passed': False,
            'error_type': type(error).__name__, 'details_withheld': True, 'at_utc': utc_now()})
        raise SystemExit('Post-change verification failed; private details withheld') from None


if __name__ == '__main__':
    main()
