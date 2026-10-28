from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
import os

import pytest
import yaml

from benchmark.adapters import protected as protected
from benchmark.compare import compare_metrics, compare_reports
from benchmark.db_time import DbTimeMonitor, db_time_delta, monitoring_parameters
from datagen.model import COLUMNS
from dprcrypto import encrypt


@pytest.fixture
def profile():
    return yaml.safe_load(Path('policy/protection_profile.yaml').read_text(encoding='utf-8'))


@pytest.fixture
def protected_record(source, profile):
    identity, pii, finance = uuid4(), os.urandom(32), os.urandom(32)
    row = dict(anggota_id=identity, legacy_row_id=source[0]['id'], protection_version=1,
               dek_pii_wrapped='synthetic_pii_marker', dek_fin_wrapped='synthetic_fin_marker')
    for name, cfg in profile['columns'].items():
        value = source[0][name]
        value = value.isoformat() if isinstance(value, date) else str(value) if value is not None else None
        row[cfg['storage_column']] = encrypt(value, pii if cfg['domain']=='PII' else finance,
            column=name, anggota_id=identity) if cfg['aead'] else value
    return row, pii, finance


def test_real_crypto_selective_domains_and_aad(source, profile, protected_record):
    row, pii, finance = protected_record
    manager = MagicMock()
    manager.unwrap_many.side_effect = lambda kek, values: [pii if kek=='pii-kek' else finance]*len(values)
    result = protected.decrypt_rows([row], COLUMNS, profile, manager)
    assert result == [tuple(source[0][c] for c in COLUMNS)]
    assert manager.unwrap_many.call_count == 2
    manager.reset_mock()
    assert protected.decrypt_rows([row], ('id','nama','jenis_kelamin'), profile, manager)[0][1] == source[0]['nama']
    assert manager.unwrap_many.call_args.args[0] == 'pii-kek'
    assert manager.unwrap_many.call_count == 1
    assert protected.decrypt_rows([], COLUMNS, profile, manager) == []
    row['anggota_id'] = uuid4()
    with pytest.raises(Exception, match='authentication failed'):
        protected.decrypt_rows([row], ('nama',), profile, manager)
    assert protected.business_value('jumlah_anak',None) is None


def test_endpoint_and_monitoring_guards(monkeypatch):
    monkeypatch.setenv('PROTECTED_DATABASE_URL','host=127.0.0.1 port=5433 user=app_user sslmode=verify-full sslrootcert=ca.crt')
    assert protected.protected_parameters('protected_1m')['dbname']=='protected_1m'
    with pytest.raises(ValueError): protected.protected_parameters('postgres')
    monkeypatch.setenv('PROTECTED_DATABASE_URL','host=127.0.0.1 port=5433 user=postgres sslmode=disable')
    with pytest.raises(ValueError): protected.protected_parameters('protected_1m')
    monkeypatch.setenv('BENCH_MONITOR_DATABASE_URL','host=127.0.0.1 port=5433 user=postgres sslmode=verify-full sslrootcert=ca.crt dbname=protected_100k')
    assert monitoring_parameters()['user']=='postgres'
    monkeypatch.setenv('BENCH_MONITOR_DATABASE_URL','host=127.0.0.1 port=5433 user=app_user sslmode=verify-full sslrootcert=ca.crt')
    with pytest.raises(ValueError): monitoring_parameters()


def test_connect_identity_policy_cleanup(monkeypatch,profile):
    conn, client = MagicMock(), MagicMock()
    conn.execute.return_value.fetchone.return_value={'role':'app_user','ssl':True}
    monkeypatch.setattr(protected,'protected_parameters',lambda db:{})
    monkeypatch.setattr(protected.psycopg,'connect',lambda **k:conn)
    monkeypatch.setattr(protected,'OpenBaoClient',lambda:client)
    monkeypatch.setenv('DPR_BENCH_PRINCIPAL',str(uuid4()))
    adapter=protected.ProtectedAdapter({},profile=profile)
    session=adapter.connect()
    client.require_policy.assert_called_once_with('svc-app')
    assert session.manager._ttl==0 and session.manager._maximum==0
    session.close()
    assert client.close.called and conn.close.called
    conn.execute.return_value.fetchone.return_value={'role':'postgres','ssl':True}
    with pytest.raises(ValueError): adapter.connect()
    conn.execute.return_value.fetchone.return_value={'role':'app_user','ssl':True}
    client.require_policy.side_effect=ValueError('withheld')
    with pytest.raises(ValueError): adapter.connect()


def test_all_operations_bindings_rollback_and_results(source,profile,protected_record,monkeypatch):
    record, pii, finance=protected_record
    keys={'profiles':source,'pages':[{'anchor':0,'rows':[[source[0]['id'],source[0]['nama'],source[0]['jenis_kelamin']]]}], 'insert_templates':source[:8]}
    adapter=protected.ProtectedAdapter(keys,profile=profile)
    manager=MagicMock(); manager.unwrap_many.side_effect=lambda kek,values:[pii if kek=='pii-kek' else finance]*len(values)
    session=SimpleNamespace(connection=MagicMock(),manager=manager,indexer=MagicMock(),client=MagicMock())
    session.connection.execute.return_value.fetchall.return_value=[record]
    session.connection.execute.return_value.rowcount=1
    for op in protected.READS:
        assert adapter.execute(session,op,0,0)
    assert session.indexer.digest.call_count==2
    original=adapter.select
    monkeypatch.setattr(adapter,'select',MagicMock(side_effect=[([record],[]),([],[ (source[0]['id'],source[0]['handphone']) ])]))
    assert adapter.execute(session,'update_contact',0,0)
    monkeypatch.setattr(adapter,'select',MagicMock(return_value=([],[])))
    with pytest.raises(ValueError): adapter.execute(session,'update_contact',0,0)
    monkeypatch.setattr(adapter,'select',MagicMock(return_value=([record],[])))
    session.connection.execute.return_value.rowcount=0
    with pytest.raises(ValueError): adapter.execute(session,'update_contact',0,0)
    template=dict(source[0],id=-1)
    monkeypatch.setattr(protected,'protect_batch',lambda *a:[dict.fromkeys(protected.target_columns(profile),'synthetic')])
    monkeypatch.setattr(adapter,'select',MagicMock(return_value=([],[tuple(template[c] for c in COLUMNS)])))
    assert adapter.execute(session,'insert_member',0,0)
    assert all(call.kwargs['force_rollback'] for call in session.connection.transaction.call_args_list)
    monkeypatch.setattr(adapter,'select',MagicMock(return_value=([],[])))
    with pytest.raises(ValueError,match='withheld'): adapter.execute(session,'read_profile',0,0)
    with pytest.raises(ValueError): adapter.execute(session,'unknown',0,0)
    monkeypatch.setattr(adapter,'select',original)


def test_db_time_counters_and_separate_connection(monkeypatch):
    before={'reset':'same','dealloc':0,'rows':{'1':(10,2.)}}
    after={'reset':'same','dealloc':0,'rows':{'1':(12,3.),'2':(1,2.)}}
    assert db_time_delta(before,after,2)['db_time_ms_per_request']==1.5
    for modified in [dict(after,reset='changed'),dict(after,dealloc=1),dict(after,rows={}),dict(after,rows={'1':(9,3.)})]:
        with pytest.raises(ValueError): db_time_delta(before,modified,2)
    with pytest.raises(ValueError): db_time_delta(before,before,2)
    with pytest.raises(ValueError): db_time_delta(before,after,0)
    import benchmark.db_time as db
    monkeypatch.setattr(db,'monitoring_parameters',lambda:{})
    conn=MagicMock()
    conn.execute.return_value.fetchone.return_value=('reset',0)
    conn.execute.return_value.fetchall.return_value=[(1,2,3.)]
    monkeypatch.setattr(db.psycopg,'connect',lambda **k:conn)
    monitor=DbTimeMonitor('protected_100k','app_user')
    assert monitor.snapshot()['rows']=={'1':(2,3.)}
    assert conn.execute.call_args.args[1]==('protected_100k','app_user')
    conn.execute.return_value.fetchall.return_value=[(None,2,3.)]
    with pytest.raises(ValueError): monitor.snapshot()
    monitor.close(); conn.close.assert_called_once()
    with pytest.raises(ValueError): DbTimeMonitor('postgres','app_user')


def test_compare_absolute_and_ratio_separate(tmp_path):
    before={'p50_ms':1.,'p95_ms':2.,'throughput_rps':100.,'error_rate':0.}
    after=dict(before,p95_ms=6.,throughput_rps=75.)
    row=compare_metrics(before,after,'read_profile')
    assert row['P01_absolute_passed'] and not row['P01_ratio_passed']
    assert row['P02_passed'] and row['P03_passed']
    assert compare_metrics(before,dict(after,p95_ms=11.),'mixed')['P01_absolute_passed']
    assert not compare_metrics(before,dict(after,p95_ms=13.),'insert_member')['P01_absolute_passed']
    assert compare_reports({'read_profile':before},{'read_profile':after},tmp_path)
    with pytest.raises(ValueError): compare_metrics(before,after,'unknown')
    with pytest.raises(ValueError): compare_metrics(dict(before,p95_ms=0),after,'mixed')


def test_compare_cli(monkeypatch,tmp_path):
    import json
    import sys
    import benchmark.compare as compare
    values={'scenario':'read_profile','p50_ms':1.,'p95_ms':2.,'throughput_rps':100.,'error_rate':0.}
    source=tmp_path/'source'; source.mkdir()
    (source/'summary.json').write_text(json.dumps({'median_between_runs':[values]}))
    monkeypatch.setattr(sys,'argv',['compare','--before',str(source),'--after',str(source/'summary.json'),'--out',str(tmp_path/'out')])
    compare.main()
    assert (tmp_path/'out/comparison.json').is_file()


def test_runner_collects_db_time_outside_request_loop(monkeypatch,tmp_path):
    import benchmark.runner as runner
    from benchmark.tests.test_runner_metrics import MANIFEST
    collector=MagicMock(); collector.thread=None
    collector.finish.return_value={'samples':1,'failed_samples':0}
    monkeypatch.setattr(runner,'Collector',lambda *a:collector)
    adapter=MagicMock()
    monitor=MagicMock()
    monitor.snapshot.side_effect=[{'reset':'same','dealloc':0,'rows':{}},
                                 {'reset':'same','dealloc':0,'rows':{'1':(10,1.)}}]
    result=runner.one_run(adapter,'read_profile',1,MANIFEST,1,.01,.001,tmp_path/'run',db_monitor=monitor)
    assert result['db_time']['calls']==10
    assert monitor.snapshot.call_count==2
