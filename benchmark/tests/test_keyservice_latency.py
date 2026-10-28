from types import SimpleNamespace
from unittest.mock import MagicMock
import os

import pytest
import yaml

from benchmark.adapters.protected import (cache_configuration, protect_insert, decrypt_rows,
                                         ProtectedAdapter, ProtectedConnection)
from benchmark.keyservice_diagnose import WireTrace, measure
from datagen.model import COLUMNS
from dprcrypto import decrypt, index_message
from pathlib import Path


def test_bounded_cache_config_and_telemetry(monkeypatch):
    monkeypatch.delenv('DPR_BENCH_DEK_CACHE_TTL', raising=False)
    monkeypatch.delenv('DPR_BENCH_DEK_CACHE_ENTRIES', raising=False)
    assert cache_configuration() == (0, 0)
    monkeypatch.setenv('DPR_BENCH_DEK_CACHE_TTL', '60')
    assert cache_configuration() == (60, 4096)
    session = ProtectedConnection(MagicMock(), MagicMock())
    assert ProtectedAdapter.telemetry(None, [session])['max_entries'] == 4096
    assert ProtectedAdapter.telemetry(None, [])['workers'] == 0
    session.close()
    for value in ('61', '-1', 'nan', 'inf', 'bad'):
        monkeypatch.setenv('DPR_BENCH_DEK_CACHE_TTL', value)
        with pytest.raises(ValueError): cache_configuration()
    monkeypatch.setenv('DPR_BENCH_DEK_CACHE_TTL', '1')
    monkeypatch.setenv('DPR_BENCH_DEK_CACHE_ENTRIES', '4097')
    with pytest.raises(ValueError): cache_configuration()


def test_insert_uses_one_hmac_batch_and_contract_crypto(source):
    profile = yaml.safe_load(Path('policy/protection_profile.yaml').read_text())
    pii, fin = os.urandom(32), os.urandom(32)
    manager, indexer = MagicMock(), MagicMock()
    manager.create_record_keys.return_value = SimpleNamespace(
        pii=SimpleNamespace(dek=pii, wrapped='synthetic-pii'),
        finance=SimpleNamespace(dek=fin, wrapped='synthetic-fin'))
    digests = [os.urandom(32) for _ in range(3)]
    indexer.digests.return_value = digests
    session = SimpleNamespace(manager=manager, indexer=indexer)
    result = protect_insert(source[0], profile, session)
    indexer.digests.assert_called_once()
    assert [c for c, _ in indexer.digests.call_args.args[0]] == [c for c, p in profile['columns'].items() if p['bidx']]
    manager.unwrap_many.side_effect = lambda kek, values: [pii if kek == 'pii-kek' else fin]
    assert decrypt_rows([result], COLUMNS, profile, manager) == [tuple(source[0][c] for c in COLUMNS)]
    for (column, _), digest in zip(indexer.digests.call_args.args[0], digests):
        assert result[profile['columns'][column]['bidx_column']] == digest


def test_safe_trace_and_bounded_measurement():
    trace = WireTrace()
    request = SimpleNamespace(extensions={})
    trace.attach(request)
    assert request.extensions['trace'] is trace
    trace('connection.start_tls.started', {'secret': 'DO_NOT_RETAIN'})
    trace('connection.start_tls.complete', {'secret': 'DO_NOT_RETAIN'})
    assert trace.report()['events']['connection.start_tls.started'] == 1
    assert 'DO_NOT_RETAIN' not in str(trace.report())
    fn = MagicMock()
    assert measure([fn], 100)['requests'] == 100
    assert fn.call_count == 100
    assert measure([lambda i: None] * 8, 200)['requests'] == 200
    for calls in (99, 501, 201):
        with pytest.raises(ValueError): measure([fn] * 8, calls)


def test_runner_records_cache_delta_excluding_warmup(monkeypatch, tmp_path):
    import benchmark.runner as runner
    from benchmark.tests.test_runner_metrics import MANIFEST
    collector = MagicMock()
    collector.thread = None
    collector.finish.return_value = {'samples': 1, 'failed_samples': 0}
    monkeypatch.setattr(runner, 'Collector', lambda *a: collector)
    class Adapter:
        count = 0
        def connect(self): return MagicMock()
        def execute(self, *args): self.count += 1
        def telemetry(self, sessions):
            return dict(hits=self.count, misses=0, remote_batches=0)
    result = runner.one_run(Adapter(), 'read_by_nik', 1, MANIFEST, 1, .02, .005, tmp_path / 'run')
    trace = result['adapter_telemetry']
    assert trace['before_measurement']['hits'] > 0
    assert trace['measurement']['hits'] == result['requests']
    assert trace['measurement']['hit_rate'] == 1


def test_verification_gate_prevents_smoke_and_sanitizes_failure(monkeypatch, tmp_path):
    import json
    import benchmark.keyservice_verify as verify
    monkeypatch.setattr(verify, 'BASE', tmp_path)
    monkeypatch.setattr(verify, 'services', lambda: None)
    (tmp_path / 'parity_cache_0.json').write_text(json.dumps({'passed': False}))
    with pytest.raises(RuntimeError, match='gate'):
        verify.smoke()
    monkeypatch.setattr(verify, 'verify_parity', MagicMock(side_effect=RuntimeError('PRIVATE_FAILURE_CONTENT')))
    monkeypatch.setattr(verify.os.sys, 'argv', ['verify', 'parity'])
    with pytest.raises(SystemExit):
        verify.main()
    assert 'PRIVATE_FAILURE_CONTENT' not in (tmp_path / 'parity_failure.json').read_text()


def test_parity_verifies_both_cache_variants(monkeypatch, tmp_path):
    import benchmark.keyservice_verify as verify
    calls = []
    def fake(path, samples):
        calls.append((path.name, samples, os.environ['DPR_BENCH_DEK_CACHE_TTL']))
        return {'passed': True}
    monkeypatch.setattr(verify, 'BASE', tmp_path)
    monkeypatch.setattr(verify, 'parity_run', fake)
    monkeypatch.setenv('DPR_BENCH_DEK_CACHE_TTL', '0')
    assert len(verify.verify_parity()) == 2
    assert calls == [('parity_cache_0.json', 1000, '0'), ('parity_cache_60.json', 1000, '60')]
    monkeypatch.setattr(verify, 'parity_run', lambda *a, **k: {'passed': False})
    with pytest.raises(RuntimeError):
        verify.verify_parity()
