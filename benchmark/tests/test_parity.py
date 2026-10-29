from unittest.mock import MagicMock
import json

import pytest

from benchmark import parity


def test_distinct_parity_keys_do_not_change_benchmark_corpus(source):
    keys={'profiles':source,'pages':[{'anchor':0,'rows':[]}],'insert_templates':source[:8]}
    conn=MagicMock()
    conn.execute.return_value.fetchall.return_value=[(1,'HandmadeFixture','L')]
    result=parity.parity_keys(keys,conn,100000,10)
    assert len(result['profiles'])==10 and len(result['pages'])==10
    assert len({p['anchor'] for p in result['pages']})==10
    assert len(keys['pages'])==1
    assert all(len(call.args)==2 for call in conn.execute.call_args_list)
    with pytest.raises(ValueError): parity.parity_keys(keys,conn,100000,1000)


def test_trusted_scope_setup_cleanup(source):
    keys={'profiles':source[:2],'pages':[{'rows':[[3,'HandmadeFixture','L']]}]}
    conn=MagicMock()
    conn.execute.return_value.fetchone.return_value=(3,)
    principal,count=parity.prepare_scope(conn,keys)
    assert count==3 and principal
    conn.execute.return_value.fetchone.return_value=(0,)
    parity.remove_scope(conn,principal)
    conn.execute.return_value.fetchone.return_value=(2,)
    with pytest.raises(ValueError): parity.prepare_scope(conn,keys)
    with pytest.raises(ValueError): parity.remove_scope(conn,principal)


def test_dataset_correctness_and_cleanup(monkeypatch,source):
    keys={'profiles':source[:2],'pages':[{'anchor':0,'rows':[[1,'HandmadeFixture','L']]}],'insert_templates':source[:8]}
    monkeypatch.setattr(parity,'load_keys',lambda *a:(keys,{'sha256':'aggregate'}))
    monkeypatch.setattr(parity,'parameters',lambda *a:{})
    monkeypatch.setattr(parity,'monitoring_parameters',lambda:{})
    monkeypatch.setattr(parity,'parity_keys',lambda *a:keys)
    monkeypatch.setattr(parity,'prepare_scope',lambda *a:('synthetic-principal',2))
    cleanup=MagicMock(); monkeypatch.setattr(parity,'remove_scope',cleanup)
    conn=MagicMock(); conn.__enter__.return_value=conn
    monkeypatch.setattr(parity.psycopg,'connect',lambda **k:conn)
    plain,adapter,session=MagicMock(),MagicMock(),MagicMock()
    plain.execute.return_value=adapter.execute.return_value=[('handmade',)]
    adapter.connect.return_value=session
    monkeypatch.setattr(parity,'PlaintextAdapter',lambda *a:plain)
    monkeypatch.setattr(parity,'ProtectedAdapter',lambda *a:adapter)
    monitor=MagicMock()
    monitor.snapshot.side_effect=[{'reset':'same','dealloc':0,'rows':{'1':(i,float(i))}} for i in range(8)]
    monkeypatch.setattr(parity,'DbTimeMonitor',lambda *a:monitor)
    monkeypatch.delenv('DPR_BENCH_PRINCIPAL',raising=False)
    result=parity.check_dataset('baseline_100k','protected_100k',100000,2)
    assert result['passed'] and len(result['scenarios'])==4
    cleanup.assert_called_once_with(conn,'synthetic-principal')
    session.close.assert_called_once(); monitor.close.assert_called_once()
    assert 'DPR_BENCH_PRINCIPAL' not in parity.os.environ
    monkeypatch.setenv('DPR_BENCH_PRINCIPAL','previous')
    adapter.execute.return_value=[('different handmade',)]
    monitor.snapshot.side_effect=None
    with pytest.raises(ValueError): parity.check_dataset('baseline_100k','protected_100k',100000,2)
    assert parity.os.environ['DPR_BENCH_PRINCIPAL']=='previous'


def test_gate_report_and_cli_fail_closed(monkeypatch,tmp_path):
    monkeypatch.setattr(parity,'check_dataset',lambda *a:{'passed':True})
    output=tmp_path/'parity.json'
    assert parity.run(output,2)['passed']
    monkeypatch.setattr(parity,'check_dataset',MagicMock(side_effect=RuntimeError('sensitive values never copied')))
    assert not parity.run(output,2)['passed']
    assert 'sensitive values' not in output.read_text()
    monkeypatch.setattr(parity,'run',lambda *a:{'passed':True})
    monkeypatch.setattr(parity.os.sys,'argv',['parity','--out',str(output)])
    with pytest.raises(SystemExit) as result: parity.main()
    assert result.value.code==0
