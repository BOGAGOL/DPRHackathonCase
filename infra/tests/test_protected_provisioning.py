"""Provisioning guards and secret handling, with synthetic ephemeral credentials."""

import json
import secrets
from types import SimpleNamespace

import pytest
import yaml

from infra.protected import apply, credentials
from infra.security import REPO


def test_profile_rejects_stale_decisions(tmp_path):
    profile=apply.load_profile(REPO/"policy/protection_profile.yaml")
    profile["columns"]["kode_bank"]["aead"]=False
    path=tmp_path/"stale.yaml";path.write_text(yaml.safe_dump(profile))
    with pytest.raises(ValueError,match="stale"):apply.load_profile(path)
    assertion=apply.schema_check_sql(apply.load_profile(REPO/"policy/protection_profile.yaml"))
    assert "nama_ct" in assertion and "rekening_ct" in assertion and "Unexpected object ownership" in assertion


def test_provision_atomic_env_secrets_and_cluster_guard(monkeypatch):
    passwords={role:secrets.token_urlsafe(32) for role in credentials.ROLES}
    calls=[]
    def run(command,**kwargs):
        calls.append((command,kwargs));return SimpleNamespace(returncode=0)
    monkeypatch.setattr(apply.subprocess,"run",run)
    monkeypatch.setenv("DPR_DOCKER_CONTEXT","synthetic-context")
    apply.provision("synthetic-container","protected_734","synthetic-admin",passwords,
                    apply.load_profile(REPO/"policy/protection_profile.yaml"),system_identifier="123456")
    command,kwargs=calls[0]
    assert command[:3]==["docker","--context","synthetic-context"]
    script=kwargs["input"]
    assert "BEGIN;" in script and script.endswith("COMMIT;\n") and "pg_control_system()" in script
    assert "log_min_error_statement='panic'" in script and "dpr_role_bootstrap_only false" in script
    assert kwargs["capture_output"] and kwargs["timeout"]==180
    for role,password in passwords.items():
        assert password not in script and password not in command
        assert kwargs["env"][credentials.role_environment(role)]==password
    monkeypatch.setattr(apply.subprocess,"run",lambda *a,**kw:SimpleNamespace(returncode=3,stderr=secrets.token_urlsafe(32)))
    with pytest.raises(RuntimeError,match="details withheld"):
        apply.provision("synthetic-container","protected_734","synthetic-admin",passwords,{"columns":{}})


@pytest.mark.parametrize("problem",["source","missing_role","short_secret","newline","identity"])
def test_provision_rejects_unsafe_inputs_before_docker(problem,monkeypatch):
    passwords={role:secrets.token_urlsafe(32) for role in credentials.ROLES}
    database="protected_734";identity=None
    if problem=="source":database="postgres"
    elif problem=="missing_role":passwords.pop("app_user")
    elif problem=="short_secret":passwords["app_user"]=secrets.token_hex(4)
    elif problem=="newline":passwords["app_user"]+="\n"
    else:identity="123'; SELECT 1"
    def forbidden(*a,**kw):pytest.fail("Docker must not run for invalid input")
    monkeypatch.setattr(apply.subprocess,"run",forbidden)
    with pytest.raises(ValueError):apply.provision("fixture",database,"admin",passwords,{"columns":{}},system_identifier=identity)


def test_role_env_and_private_credential_lifecycle(tmp_path,monkeypatch):
    for role in credentials.ROLES:monkeypatch.delenv(credentials.role_environment(role),raising=False)
    with pytest.raises(ValueError):credentials.role_environment("postgres")
    value=secrets.token_urlsafe(32)
    monkeypatch.setenv("DPR_APP_USER_PASSWORD",value)
    assert credentials.role_password(tmp_path,"app_user")==value
    monkeypatch.delenv("DPR_APP_USER_PASSWORD")
    monkeypatch.setattr(credentials,"secure_directory",lambda path:(path.mkdir(parents=True,exist_ok=True) or path))
    # Stub serialization represents DPAPI ciphertext, never plaintext credential data.
    monkeypatch.setattr(credentials,"powershell",lambda script,env:'<SS N="Password">encrypted-synthetic-payload</SS>')
    created=credentials.role_password(tmp_path,"app_user",create=True)
    saved=tmp_path/"postgres/roles/app_user.credential.xml"
    assert created not in saved.read_text()
    monkeypatch.setattr(credentials,"powershell",lambda script,env:created)
    assert credentials.role_password(tmp_path,"app_user")==created
    with pytest.raises(ValueError):credentials.role_password(tmp_path,"analyst_user")
    monkeypatch.setattr(credentials,"powershell",lambda script,env:env["DPR_CREDENTIAL_INPUT"])
    with pytest.raises(RuntimeError):credentials.role_password(tmp_path,"auditor_user",create=True)
    monkeypatch.setenv("DPR_APP_USER_PASSWORD",secrets.token_hex(3))
    with pytest.raises(ValueError):credentials.role_password(tmp_path,"app_user")


def test_admin_parameters_verify_tls_and_project_port(tmp_path,monkeypatch):
    monkeypatch.setenv("PGUSER","synthetic-admin");monkeypatch.setenv("PGPASSWORD",secrets.token_urlsafe(32))
    monkeypatch.delenv("PGPORT",raising=False)
    params=apply.admin_parameters(tmp_path,"protected_734")
    assert params["sslmode"]=="verify-full" and params["port"]==5433
    monkeypatch.setenv("PGPORT","5434")
    with pytest.raises(ValueError):apply.admin_parameters(tmp_path,"protected_734")
    monkeypatch.delenv("PGUSER")
    monkeypatch.setattr(apply,"local_admin_parameters",lambda root,database:{"dbname":database})
    assert apply.admin_parameters(tmp_path,"protected_100k")["dbname"]=="protected_100k"


def test_cli_records_success_and_redacts_failures(tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(apply,"REPO",tmp_path)
    profile=tmp_path/"profile.yaml";profile.write_text("synthetic")
    monkeypatch.setattr("sys.argv",["apply","--database","protected_734","--profile",str(profile)])
    monkeypatch.setattr(apply,"external_directory",lambda value:tmp_path)
    monkeypatch.setattr(apply,"load_profile",lambda path:{})
    monkeypatch.setattr(apply,"admin_parameters",lambda *a:{})
    class Connection:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,*args):return SimpleNamespace(fetchone=lambda:(180006,"synthetic-admin","123456"))
    monkeypatch.setattr(apply.psycopg,"connect",lambda **kw:Connection())
    monkeypatch.setattr(apply,"role_password",lambda *a,**kw:secrets.token_urlsafe(32))
    monkeypatch.setattr(apply,"provision",lambda *a,**kw:None)
    monkeypatch.setattr(apply,"inspect_schema",lambda *a:{"passed":True,"checks":{},"row_counts":{}})
    apply.main()
    report=tmp_path/"evidence/schema/protected_734.json"
    assert json.loads(report.read_text())["passed"]
    secret=secrets.token_urlsafe(32)
    def failure(*args):raise ValueError(secret)
    monkeypatch.setattr(apply,"load_profile",failure)
    with pytest.raises(SystemExit):apply.main()
    assert secret not in report.read_text()+capsys.readouterr().out
    assert not json.loads(report.read_text())["passed"]
