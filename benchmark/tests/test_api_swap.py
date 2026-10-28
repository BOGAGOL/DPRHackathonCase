import copy
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from benchmark.api import db_swap as d


class Store:
    def __init__(self):
        self.data={'baseline_100k':{'oid':11,'allow_connections':True},'protected_100k':{'oid':22,'allow_connections':True}}
        self.active=set();self.dropped=[];self.calls=[];self.fail_clone=None
    def entries(self):return copy.deepcopy(self.data)
    def sessions(self,oid):return int(oid in self.active)
    def rename(self,a,b):self.calls.append(('rename',a,b));self.data[b]=self.data.pop(a)
    def allow(self,n,enabled):self.data[n]['allow_connections']=enabled
    def clone(self,n,t):
        if n==self.fail_clone:raise RuntimeError('synthetic_clone_failure')
        self.data[n]={'oid':self.data[t]['oid']+100,'allow_connections':True}
    def drop_copy(self,n,oid):
        assert self.data[n]['oid']==oid and oid not in (11,22)
        self.dropped.append(oid);del self.data[n]


def test_full_swap_journal_and_idempotent_restore_drop_only_copies(tmp_path):
    store=Store();before=store.entries();p=tmp_path/'state.json';swap=d.Swap(store,p)
    swap.swap()
    state=json.loads(p.read_text())
    assert state['status']=='swapped' and state['copies']=={'baseline_100k':111,'protected_100k':122}
    assert not store.data['baseline_100k__official']['allow_connections']
    swap=d.Swap(store,p);swap.restore()
    assert store.entries()==before and store.dropped==[111,122]
    assert swap.state['status']=='names_restored_pending_verification'
    swap.state['verification']={'passed':True};swap.save('restored');swap.restore()
    assert store.dropped==[111,122]


def test_partial_clone_failure_restores_both_original_names(tmp_path):
    store=Store();before=store.entries();store.fail_clone='protected_100k'
    swap=d.Swap(store,tmp_path/'state.json')
    with pytest.raises(RuntimeError):swap.swap()
    swap.restore()
    assert store.entries()==before and store.dropped==[111]


@pytest.mark.parametrize('failure',['session','archive','missing'])
def test_initial_gate_refuses_mutation_on_sessions_or_collisions(tmp_path,failure):
    store=Store()
    if failure=='session':store.active.add(11)
    elif failure=='archive':store.data['baseline_100k__official']={'oid':99}
    else:del store.data['baseline_100k']
    swap=d.Swap(store,tmp_path/'state.json')
    with pytest.raises(RuntimeError):swap.swap()
    assert not store.calls and not swap.path.exists()


@pytest.mark.parametrize('failure',['unknown_copy','wrong_original','missing_original','unknown_copy_after_crash'])
def test_recovery_fails_closed_without_dropping_unknown_oid(tmp_path,failure):
    store=Store();swap=d.Swap(store,tmp_path/'state.json');swap.swap()
    if failure=='unknown_copy':store.data['baseline_100k']['oid']=999
    elif failure=='wrong_original':store.data['baseline_100k__official']['oid']=999
    elif failure=='missing_original':del store.data['baseline_100k__official']
    else:del swap.state['copies']['baseline_100k']
    with pytest.raises(RuntimeError,match='recovery_failed'):swap.restore()
    assert not store.dropped and swap.state['status']=='restore_failed'


def test_existing_journal_is_never_overwritten(tmp_path):
    store=Store();p=tmp_path/'state.json';swap=d.Swap(store,p);swap.swap()
    with pytest.raises(RuntimeError,match='existing_swap_journal'):d.Swap(store,p).swap()


def test_pg_store_uses_local_separate_admin_and_identifier_guards(monkeypatch):
    conn=MagicMock();conn.execute.return_value.fetchone.return_value=(True,)
    monkeypatch.setattr(d,'monitoring_parameters',lambda:{'host':'127.0.0.1','port':'5433','user':'postgres','sslmode':'verify-full'})
    connect=MagicMock(return_value=conn);monkeypatch.setattr(d.psycopg,'connect',connect)
    store=d.PGStore()
    assert connect.call_args.kwargs['dbname']=='template1' and connect.call_args.kwargs['sslmode']=='verify-full'
    for operation in [lambda:store.rename('postgres','x'),lambda:store.allow('postgres',False),lambda:store.clone('postgres','x')]:
        with pytest.raises(ValueError):operation()
    store.rename('baseline_100k','baseline_100k__official');store.allow('baseline_100k__official',False)
    store.clone('baseline_100k','baseline_100k__official')
    monkeypatch.setattr(store,'entries',lambda:{'baseline_100k':{'oid':111}})
    with pytest.raises(RuntimeError):store.drop_copy('baseline_100k',11)
    store.drop_copy('baseline_100k',111);store.sessions(11);store.close()
    conn.close.assert_called_once()
    monkeypatch.setattr(d,'monitoring_parameters',lambda:{'host':'43.156.157.247','port':'5432','user':'postgres'})
    with pytest.raises(RuntimeError):d.PGStore()
