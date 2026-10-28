"""Bounded component diagnosis; never export arguments, responses, or key material."""

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import threading
import time
import hashlib
import subprocess
from uuid import uuid4

import yaml

from dprcrypto import OpenBaoClient, decrypt, encrypt
from infra.openbao.api import from_environment
from infra.openbao.init import save_response
from .adapters.plaintext import PlaintextAdapter, load_keys, SELECT
from .adapters.protected import ProtectedAdapter
from .common import ROOT, utc_now, write_json
from .collect_metrics import Collector
from .paired import CONTAINERS, admin_parameters, services
from .parity import prepare_scope, remove_scope
from .stats import summarize
import psycopg
from psycopg import sql


class WireTrace:
    """Record only event names/durations; never retain httpcore info payloads."""
    def __init__(self):
        self.counts = Counter()
        self.starts = {}
        self.durations = defaultdict(list)

    def __call__(self, name, info):
        self.counts[name] += 1
        if name.endswith('.started'):
            self.starts[name.rsplit('.', 1)[0]] = time.perf_counter()
        elif name.endswith('.complete'):
            key = name.rsplit('.', 1)[0]
            if key in self.starts:
                self.durations[key].append((time.perf_counter() - self.starts.pop(key)) * 1000)

    def attach(self, request):
        request.extensions['trace'] = self

    def report(self):
        return {'events': dict(self.counts), 'mean_event_ms': {
            k: sum(v) / len(v) for k, v in self.durations.items() if v}}


def measure(functions, calls):
    """One persistent client per worker; exactly calls samples across workers."""
    if not 100 <= calls <= 500 or not functions or calls % len(functions):
        raise ValueError('Invalid bounded component sample')
    barrier = threading.Barrier(len(functions))
    def worker(index):
        barrier.wait()
        samples = []
        for i in range(calls // len(functions)):
            start = time.perf_counter()
            functions[index](i)
            samples.append((time.perf_counter() - start) * 1000)
        return samples
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=len(functions)) as pool:
        values = sum(pool.map(worker, range(len(functions))), [])
    return summarize(values, 0, time.perf_counter() - start)


def run(output=ROOT / 'evidence/benchmark/keyservice_diagnosis.json', calls=200):
    production_files = ['toolkit/dprcrypto/openbao.py', 'toolkit/dprcrypto/keys.py',
                        'toolkit/dprcrypto/bidx.py', 'benchmark/adapters/protected.py']
    reference = json.loads((ROOT / 'evidence/benchmark/naive_v1.json').read_text())['production_commit']
    hashes = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in production_files}
    reference_hashes = {p: hashlib.sha256(subprocess.check_output(['git', 'show', reference + ':' + p])).hexdigest()
                        for p in production_files}
    # Git stores LF; hash comparison uses text normalized to LF on Windows.
    changed = any(subprocess.check_output(['git', 'show', reference + ':' + p]).decode().replace('\r\n', '\n')
                  != (ROOT / p).read_text().replace('\r\n', '\n') for p in production_files)
    report = {'started_at_utc': utc_now(), 'kind': 'bounded_diagnosis_not_official_benchmark',
              'production_code_changed_before_measurement': changed, 'calls_per_case': calls,
              'production_files_sha256': hashes, 'naive_production_git_blobs_sha256': reference_hashes,
              'concurrency': [1, 8], 'components': [], 'scenario_rpc_counts': {}, 'passed': False}
    services()
    manifest = yaml.safe_load((ROOT / 'benchmark/workloads.yaml').read_text())
    keys, identity = load_keys(manifest, 8, 'baseline_100k')
    report['key_corpus'] = identity
    api = from_environment()
    private = Path(os.environ['DPR_SECRETS_DIR']) / 'openbao'
    root = json.loads((private / 'init-material.json').read_text())['root_token']
    token_file = private / 'tokens' / ('svc-migration-diagnosis-' + uuid4().hex + '.json')
    response = save_response(token_file, lambda: api.request('/auth/token/create-orphan',
        {'policies': ['svc-migration'], 'no_default_policy': True, 'renewable': False,
         'ttl': '900s', 'explicit_max_ttl': '900s', 'display_name': 'bounded-datakey-diagnosis'}, token=root))
    del root
    os.environ['DPR_DIAG_MIGRATION_TOKEN'] = response['auth']['client_token']
    try:
        for concurrency in (1, 8):
            for component in ('hmac', 'unwrap', 'datakey_wrapped', 'aes_gcm_local', 'sql_plain', 'hmac_batch_3', 'unwrap_batch_50'):
                clients, connections, functions, traces = [], [], [], []
                collector = None
                try:
                    for worker in range(concurrency):
                        client = OpenBaoClient(token_env='DPR_DIAG_MIGRATION_TOKEN' if component == 'datakey_wrapped' else 'OPENBAO_TOKEN')
                        clients.append(client)
                        startup = WireTrace()
                        client._http.event_hooks['request'] = [startup.attach]
                        client.authorization_scope()
                        key = os.urandom(32)
                        wrapped = client.wrap('pii-kek', key)
                        identity = uuid4()
                        blob = encrypt('synthetic diagnosis only', key, column='nama', anggota_id=identity)
                        connection = PlaintextAdapter(keys).connect()
                        connections.append(connection)
                        if component == 'hmac':
                            fn = lambda i, c=client: c.hmac(b'bidx|v1|no_ktp|00000000000001')
                        elif component == 'unwrap':
                            fn = lambda i, c=client, w=wrapped: c.unwrap('pii-kek', w)
                        elif component == 'datakey_wrapped':
                            fn = lambda i, c=client: c._call('transit/datakey/wrapped/pii-kek', {'bits': 256})
                        elif component == 'aes_gcm_local':
                            fn = lambda i, b=blob, k=key, u=identity: decrypt(b, k, column='nama', anggota_id=u)
                        elif component == 'sql_plain':
                            fn = lambda i, c=connection: c.execute(SELECT + sql.SQL('WHERE no_ktp=%s'),
                                (keys['profiles'][i % len(keys['profiles'])]['no_ktp'],)).fetchall()
                        elif component == 'hmac_batch_3':
                            fn = lambda i, c=client: c.hmac_batch([b'bidx|v1|no_ktp|00000000000001',
                                b'bidx|v1|email|synthetic@example.com', b'bidx|v1|pengguna|synthetic'])
                        else:
                            many = client.wrap_batch('pii-kek', [os.urandom(32) for _ in range(50)])
                            fn = lambda i, c=client, w=many: c.unwrap_batch('pii-kek', w)
                        fn(0)
                        trace = WireTrace()
                        client._http.event_hooks['request'] = [trace.attach]
                        traces.append((startup, trace))
                        functions.append(fn)
                    resource_path = ROOT / 'results/bench/keyservice_diagnosis' / f'{component}_{concurrency}.csv'
                    resource_path.parent.mkdir(parents=True, exist_ok=True)
                    collector = Collector(resource_path, interval=.2, containers=CONTAINERS)
                    collector.start()
                    result = measure(functions, calls)
                    resources = collector.finish()
                    collector = None
                    report['components'].append({'component': component, 'concurrency': concurrency,
                        **result, 'resources': resources,
                        'wire_measured': [t.report() for _, t in traces],
                        'wire_startup': [t.report() for t, _ in traces]})
                    write_json(output, report)
                    print(json.dumps({'component': component, 'concurrency': concurrency,
                                      'mean_ms': result['mean_ms'], 'p95_ms': result['p95_ms']}), flush=True)
                finally:
                    if collector is not None:
                        collector.finish()
                    for connection in connections:
                        connection.close()
                    for client in clients:
                        client.close()
        with psycopg.connect(**admin_parameters('protected_100k', writable=True), autocommit=True) as admin:
            principal, _ = prepare_scope(admin, keys)
            previous = os.environ.get('DPR_BENCH_PRINCIPAL')
            os.environ['DPR_BENCH_PRINCIPAL'] = principal
            try:
                adapter = ProtectedAdapter(keys)
                session = adapter.connect()
                original = session.client._send
                counts = Counter()
                def counted(method, path, token, payload=None):
                    counts[path] += 1
                    return original(method, path, token, payload)
                session.client._send = counted
                try:
                    for scenario in manifest['scenarios'][:-1]:
                        counts.clear()
                        adapter.execute(session, scenario, 0, 0)
                        report['scenario_rpc_counts'][scenario] = dict(counts)
                finally:
                    session.close()
            finally:
                remove_scope(admin, principal)
                if previous is None:
                    os.environ.pop('DPR_BENCH_PRINCIPAL', None)
                else:
                    os.environ['DPR_BENCH_PRINCIPAL'] = previous
        report['passed'] = True
    except Exception as error:
        report.update(error_type=type(error).__name__, error='diagnosis_failed_details_withheld')
    finally:
        api.request('/auth/token/revoke-self', {}, token=os.environ.pop('DPR_DIAG_MIGRATION_TOKEN'))
        report['diagnosis_token_revoked'] = True
        report['completed_at_utc'] = utc_now()
        write_json(output, report)
    return report


if __name__ == '__main__':
    raise SystemExit(0 if run()['passed'] else 1)
