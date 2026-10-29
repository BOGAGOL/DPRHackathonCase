import os
from unittest.mock import MagicMock

import pytest

from infra.openbao.api import BaoError
from verify import attacker_setup as setup


def test_policy_issuance_no_workload_root_or_default(monkeypatch,tmp_path):
    documents=setup.policy_documents()
    assert 'finance-kek' not in documents['modc-leak-pii']
    assert 'pii-kek' not in documents['modc-leak-finance']
    assert 'decrypt/' not in documents['modc-leak-search']
    api=MagicMock()
    def request(path,payload=None,token=None):
        if path=='/auth/token/lookup-self':return {'data':{'policies':['root']}}
        if path.startswith('/sys/policies/acl/'):
            if payload is None:raise BaoError(404)
            return {}
        return {'auth':{'client_token':os.urandom(32).hex()}}
    api.request.side_effect=request
    monkeypatch.setattr(setup,'secure_directory',lambda p:(p.mkdir(parents=True,exist_ok=True) or p))
    report=setup.configure_and_issue(api,tmp_path,os.urandom(32).hex())
    assert len(report)==3
    calls=[c for c in api.request.call_args_list if c.args[0]=='/auth/token/create-orphan']
    assert all(c.args[1]['no_default_policy'] and c.args[1]['explicit_max_ttl']=='14400s' for c in calls)
    assert len(list((tmp_path/'openbao/tokens').glob('*.json')))==3
    api.request.side_effect=None
    api.request.return_value={'data':{'policies':['svc-app']}}
    with pytest.raises(ValueError):setup.configure_and_issue(api,tmp_path,'synthetic')


def test_existing_policy_mismatch_and_operator_cli(monkeypatch,tmp_path):
    api=MagicMock()
    api.request.side_effect=[{'data':{'policies':['root']}},{'data':{'policy':'unexpected permissions'}}]
    monkeypatch.setattr(setup,'secure_directory',lambda p:(p.mkdir(parents=True,exist_ok=True) or p))
    with pytest.raises(ValueError,match='differs'):setup.configure_and_issue(api,tmp_path,'synthetic')
    operation=MagicMock();monkeypatch.setattr(setup,'configure_and_issue',operation)
    monkeypatch.setattr(setup,'from_environment',lambda:api)
    monkeypatch.setenv('DPR_SECRETS_DIR',str(tmp_path));monkeypatch.setenv('OPENBAO_TOKEN',os.urandom(32).hex())
    monkeypatch.setattr('sys.argv',['setup'])
    setup.main();assert operation.called
