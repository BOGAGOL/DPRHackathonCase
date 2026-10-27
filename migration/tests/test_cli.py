import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import secrets
from types import SimpleNamespace

import pytest

from migration import cli, prepare as setup
from migration.connection import connection_parameters
from migration.model import MigrationError
from migration.runner import check_connections, execute, expected_source_rows


def test_runtime_credentials_split_and_read_only_source(tmp_path,monkeypatch):
    ca=tmp_path/"ca.crt";ca.touch()
    for name,value in {"PGSSLROOTCERT":str(ca),"PGUSER":"synthetic-reader","PGPASSWORD":secrets.token_urlsafe(32),
                       "DPR_MIGRATION_USER_PASSWORD":secrets.token_urlsafe(32)}.items():monkeypatch.setenv(name,value)
    monkeypatch.delenv("PGPORT",raising=False)
    source=cli.runtime_parameters("postgres",source=True)
    target=cli.runtime_parameters("protected_734",source=False)
    assert source["user"]=="synthetic-reader" and "read_only=on" in source["options"]
    assert target["user"]=="migration_user" and target["password"]!=source["password"]
    assert target["sslmode"]==source["sslmode"]=="verify-full" and target["port"]==5433
    monkeypatch.delenv("DPR_MIGRATION_USER_PASSWORD")
    with pytest.raises(MigrationError):cli.runtime_parameters("protected_734",source=False)
    monkeypatch.setenv("PGPORT","5434")
    with pytest.raises(ValueError):connection_parameters("postgres",source=True)
    monkeypatch.setenv("PGPORT","5433");monkeypatch.delenv("PGPASSWORD")
    with pytest.raises(ValueError):connection_parameters("postgres",source=True)
    with pytest.raises(ValueError):connection_parameters("arbitrary",source=True)


class FakeConnection:
    def __init__(self):self.queries=[];self.exists=False;self.version=180006
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def execute(self,query,values=None):
        self.queries.append((query,values))
        if "server_version_num" in str(query):return SimpleNamespace(fetchone=lambda:(self.version,"synthetic-admin","123456"))
        return SimpleNamespace(fetchone=lambda:((1,) if self.exists else None))


def test_prepare_creates_only_named_target_then_provisions(monkeypatch,tmp_path):
    connection=FakeConnection();calls=[]
    monkeypatch.setattr(setup,"load_profile",lambda path:{})
    monkeypatch.setattr(setup,"external_directory",lambda value:tmp_path)
    monkeypatch.setattr(setup,"admin_parameters",lambda root,database:{"dbname":database})
    monkeypatch.setattr(setup.psycopg,"connect",lambda **kwargs:connection)
    monkeypatch.setattr(setup,"role_password",lambda *a,**kw:secrets.token_urlsafe(32))
    monkeypatch.setattr(setup,"provision",lambda *args,**kwargs:calls.append((args,kwargs)))
    monkeypatch.setattr(setup,"inspect_schema",lambda *args:{"passed":True})
    assert setup.prepare("protected_734",tmp_path/"profile")["passed"]
    assert any("CREATE DATABASE" in str(query) for query,_ in connection.queries)
    assert calls[0][0][1]=="protected_734" and calls[0][1]["system_identifier"]=="123456"
    connection.exists=True;connection.queries=[]
    setup.prepare("protected_734",tmp_path/"profile")
    assert all("CREATE DATABASE" not in str(query) for query,_ in connection.queries)
    with pytest.raises(MigrationError):setup.prepare("postgres",tmp_path/"profile")
    connection.version=170000
    with pytest.raises(MigrationError):setup.prepare("protected_734",tmp_path/"profile")


def test_revoke_uses_only_env_and_policy_guard(monkeypatch):
    token=secrets.token_urlsafe(32);calls=[]
    monkeypatch.setenv("OPENBAO_MIGRATION_TOKEN",token)
    monkeypatch.setattr(cli,"from_environment",lambda:object())
    monkeypatch.setattr(cli,"revoke_migration",lambda api,value:calls.append(value))
    assert cli.revoke()["migration_token_revoked"] and calls==[token]
    monkeypatch.delenv("OPENBAO_MIGRATION_TOKEN")
    with pytest.raises(MigrationError):cli.revoke()


def test_readiness_reports_sealed_dependencies_without_writes(monkeypatch,tmp_path):
    monkeypatch.setattr(cli,"load_profile",lambda path:{})
    monkeypatch.setattr(cli,"from_environment",lambda:SimpleNamespace(request=lambda path:{"initialized":False,"sealed":True}))
    monkeypatch.setattr(cli,"runtime_parameters",lambda *a,**kw:{})
    class ReadOnly(FakeConnection):
        def execute(self,query,values=None):
            assert str(query).startswith(("SELECT","SHOW"))
            if str(query).startswith("SHOW"):return SimpleNamespace(fetchone=lambda:("on",))
            if "count(*)" in str(query):return SimpleNamespace(fetchone=lambda:(734,))
            if "to_regclass" in str(query) or "pg_roles" in str(query):return SimpleNamespace(fetchone=lambda:(True,))
            return SimpleNamespace(fetchone=lambda:("postgres" if not hasattr(self,"used") else "protected_734",180006))
    source=ReadOnly();target=ReadOnly();target.used=True
    pool=iter([source,target]);monkeypatch.setattr(cli.psycopg,"connect",lambda **kwargs:next(pool))
    report=cli.check_dependencies("postgres","protected_734",tmp_path/"profile")
    assert not report["passed"] and not report["checks"]["openbao_unsealed"] and not report["data_migrated"]


@pytest.mark.parametrize("command",["prepare","check","revoke"])
def test_cli_evidence_redacts_all_external_errors(command,tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(cli,"REPO",tmp_path)
    args=["migration",command]
    if command!="revoke":args += ["--target","protected_734"]
    if command=="check":args += ["--source","postgres"]
    monkeypatch.setattr("sys.argv",args)
    secret=secrets.token_urlsafe(32)
    def fail(*args,**kwargs):raise ValueError(secret)
    monkeypatch.setattr(cli,{"prepare":"prepare","check":"check_dependencies","revoke":"revoke"}[command],fail)
    with pytest.raises(SystemExit):cli.main()
    output=capsys.readouterr().out+"".join(path.read_text() for path in (tmp_path/"evidence/migration").glob("*.json"))
    assert secret not in output and "details_withheld" in output
    # Exercise successful branch too.
    monkeypatch.setattr(cli,{"prepare":"prepare","check":"check_dependencies","revoke":"revoke"}[command],lambda *a,**kw:{"passed":True})
    cli.main()


@pytest.mark.parametrize("status",["paused","validated"])
def test_cli_run_resume_status_and_default_revoke(status,tmp_path,monkeypatch):
    profile=tmp_path/"profile.yaml";profile.write_text("synthetic")
    monkeypatch.setattr(cli,"REPO",tmp_path)
    monkeypatch.setattr("sys.argv",["migration","run","--source","postgres","--target","protected_734","--profile",str(profile)])
    monkeypatch.setattr(cli,"load_profile",lambda path:{})
    monkeypatch.setattr(cli,"runtime_parameters",lambda *a,**kw:{})
    monkeypatch.setattr(cli,"OpenBaoClient",lambda **kw:FakeConnection())
    monkeypatch.setattr(cli.psycopg,"connect",lambda **kw:FakeConnection())
    monkeypatch.setattr(cli,"execute",lambda *a,**kw:{"passed":status=="validated","status":status,"complete":status=="validated"})
    calls=[];monkeypatch.setattr(cli,"revoke",lambda:(calls.append(True) or {"passed":True,"migration_token_revoked":True}))
    cli.main()
    assert bool(calls)==(status=="validated")
    name="progress" if status=="paused" else "validation"
    assert json.loads((tmp_path/"evidence/migration"/(name+".json")).read_text())["status"]==status


def test_execute_rejects_invalid_bounds_before_connections():
    for size,limit in ((0,None),(1001,None),(True,None),(100,0)):
        with pytest.raises(MigrationError):execute(None,None,source_name="postgres",target_name="protected_734",profile={},profile_hash="",
            migration_client=None,validation_client=None,batch_size=size,max_batches=limit)
    with pytest.raises(MigrationError,match="invalid_expected_row_count"):
        execute(None,None,source_name="postgres",target_name="protected_734",profile={},profile_hash="",
                migration_client=None,validation_client=None,expected_rows=True)


def test_expected_counts_are_configurable_without_opening_arbitrary_targets():
    assert expected_source_rows("postgres")==734
    assert expected_source_rows("baseline_100k")==100000
    assert expected_source_rows("baseline_1m")==1000000
    assert expected_source_rows("baseline_1m",12037)==12037
    assert expected_source_rows("baseline_100k",0)==0
    for value in (-1,True,"1000",2**63):
        with pytest.raises(MigrationError):expected_source_rows("baseline_1m",value)
    with pytest.raises(MigrationError):expected_source_rows("arbitrary",100)


@pytest.mark.parametrize("command",["run","validate","check"])
def test_cli_1m_count_override_is_forwarded(command,tmp_path,monkeypatch):
    profile=tmp_path/"profile.yaml";profile.write_text("synthetic")
    monkeypatch.setattr(cli,"REPO",tmp_path)
    args=["migration",command,"--source","baseline_1m","--target","protected_1m","--profile",str(profile),"--expected-rows","12037"]
    if command=="run":args.append("--keep-migration-token")
    monkeypatch.setattr("sys.argv",args)
    monkeypatch.setattr(cli,"load_profile",lambda path:{})
    monkeypatch.setattr(cli,"runtime_parameters",lambda *a,**kw:{})
    monkeypatch.setattr(cli,"OpenBaoClient",lambda **kw:FakeConnection())
    monkeypatch.setattr(cli.psycopg,"connect",lambda **kw:FakeConnection())
    captured={}
    def run(*a,**kwargs):captured.update(kwargs);return {"passed":True,"complete":True}
    def check(*args):captured["expected_rows"]=args[3];return {"passed":True}
    monkeypatch.setattr(cli,"execute",run);monkeypatch.setattr(cli,"check_dependencies",check)
    cli.main()
    assert captured["expected_rows"]==12037
    if command!="check":assert captured["target_name"]=="protected_1m"


def test_cli_invalid_expected_count_fails_before_crypto_or_database(tmp_path,monkeypatch):
    monkeypatch.setattr(cli,"REPO",tmp_path)
    monkeypatch.setattr("sys.argv",["migration","run","--source","baseline_1m","--target","protected_1m","--expected-rows","-1"])
    monkeypatch.setattr(cli,"OpenBaoClient",lambda **kw:pytest.fail("Must reject before connection"))
    with pytest.raises(SystemExit):cli.main()
    assert json.loads((tmp_path/"evidence/migration/validation.json").read_text())["error"]=="invalid_expected_row_count"


def test_atomic_reports_allow_concurrent_targets(tmp_path,monkeypatch):
    monkeypatch.setattr(cli,"REPO",tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda index:cli.write_report("validation",{"passed":True,"index":index}),range(16)))
    directory=tmp_path/"evidence/migration"
    assert json.loads((directory/"validation.json").read_text())["index"] in range(16)
    assert not list(directory.glob("*.tmp"))


def test_readiness_checks_real_workload_policy_not_just_presence(monkeypatch,tmp_path):
    monkeypatch.setattr(cli,"load_profile",lambda path:{})
    monkeypatch.setattr(cli,"from_environment",lambda:SimpleNamespace(request=lambda path:{"initialized":True,"sealed":False}))
    monkeypatch.setenv("OPENBAO_MIGRATION_TOKEN",secrets.token_urlsafe(32))
    monkeypatch.setenv("OPENBAO_VALIDATION_TOKEN",secrets.token_urlsafe(32))
    monkeypatch.setattr(cli,"runtime_parameters",lambda *a,**kw:{})
    monkeypatch.setattr(cli.psycopg,"connect",lambda **kw:(_ for _ in ()).throw(RuntimeError("withheld")))
    class Valid(FakeConnection):
        def require_policy(self,policy):assert policy in ("svc-migration","svc-app")
    monkeypatch.setattr(cli,"OpenBaoClient",lambda **kw:Valid())
    report=cli.check_dependencies("postgres","protected_734",tmp_path/"profile")
    assert report["checks"]["migration_policy_valid"] and report["checks"]["validation_policy_valid"]
    class Invalid(Valid):
        def require_policy(self,policy):raise RuntimeError("withheld")
    monkeypatch.setattr(cli,"OpenBaoClient",lambda **kw:Invalid())
    report=cli.check_dependencies("postgres","protected_734",tmp_path/"profile")
    assert not report["checks"]["migration_policy_valid"] and not report["checks"]["validation_policy_valid"]
