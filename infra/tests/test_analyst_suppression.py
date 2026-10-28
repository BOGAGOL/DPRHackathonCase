"""Operator interface tests; SQL permission/suppression proofs use real PG18 separately."""

import json
import secrets
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from infra.protected import analyst


def metadata_connection(*, isolated=True, barrier=True, columns=True):
    connection=MagicMock()
    results=[(isolated,), ("schema_owner", ["security_barrier=true","security_invoker=false"] if barrier else []),
        [("dimension","text"),("value","text"),("anggota_count","bigint")] if columns else [], (True,)]
    def execute(query,*args,**kwargs):
        if query.startswith("SET LOCAL") or query.startswith("-- ACL-only"): return MagicMock()
        result=results.pop(0)
        return SimpleNamespace(fetchone=lambda:result,fetchall=lambda:result)
    connection.execute.side_effect=execute
    return connection


@pytest.mark.parametrize("broken",[None,"isolated","barrier","columns"])
def test_metadata_and_upgrade_fail_closed(broken):
    options={broken:False} if broken else {}
    checks=analyst.security_checks(metadata_connection(**options))
    assert all(checks.values()) is (broken is None)
    if broken:
        with pytest.raises(ValueError): analyst.upgrade(metadata_connection(**options))
    else:
        connection=metadata_connection()
        assert all(analyst.upgrade(connection).values())
        script=connection.execute.call_args_list[1].args[0]
        assert "HAVING count(*) >= 5" in script and "ALTER ROLE" not in script
        assert connection.execute.call_args_list[1].kwargs == {"prepare":False}


def test_connection_credentials_stay_in_env_and_tls_is_required(monkeypatch):
    password=secrets.token_urlsafe(32)
    for key,value in {"PGUSER":"invented_admin","PGPASSWORD":password,"PGSSLROOTCERT":"invented-ca.crt"}.items():
        monkeypatch.setenv(key,value)
    monkeypatch.delenv("PGSSLMODE",raising=False)
    result=analyst.parameters("protected_734")
    assert result["password"]==password and result["sslmode"]=="verify-full"
    assert result["gssencmode"]=="disable"
    assert analyst.parameters("dpr_restore_"+"a"*32)["dbname"].startswith("dpr_restore_")
    for name in ("postgres","baseline_100k","protected_bad","protected_734; DROP DATABASE x"):
        with pytest.raises(ValueError): analyst.parameters(name)
    monkeypatch.setenv("PGSSLMODE","disable")
    with pytest.raises(ValueError): analyst.parameters("protected_734")


@pytest.mark.parametrize("mode",["apply","verify","commit_failure","query_failure","bad_check"])
def test_cli_atomic_success_and_redacted_errors(mode,tmp_path,monkeypatch,capsys):
    connection=MagicMock(); connection.__enter__.return_value=connection
    secret=secrets.token_urlsafe(32)
    if mode=="commit_failure": connection.__exit__.side_effect=RuntimeError(secret)
    monkeypatch.setattr(analyst,"parameters",lambda value:{})
    monkeypatch.setattr(analyst.psycopg,"connect",lambda **kwargs:connection)
    def operation(value):
        if mode=="query_failure": raise ValueError(secret)
        return {"synthetic_check":mode!="bad_check"}
    monkeypatch.setattr(analyst,"upgrade",operation)
    monkeypatch.setattr(analyst,"security_checks",operation)
    path=tmp_path/"report.json"
    argv=["--database","protected_734","--evidence",str(path)]
    if mode=="verify": argv.append("--verify-only")
    passed=mode in {"apply","verify"}
    assert analyst.main(argv)==(0 if passed else 1)
    report=json.loads(path.read_text())
    assert report["passed"] is passed and report["member_data_modified"] is False
    assert secret not in path.read_text()+capsys.readouterr().out
    if mode=="verify": connection.execute.assert_called_once_with("SET TRANSACTION READ ONLY")
