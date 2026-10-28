"""Destructive orchestration is exercised with invented fake catalogues only."""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
from types import SimpleNamespace
from uuid import uuid4

import pytest

SPEC = importlib.util.spec_from_file_location("golden_reset_test", Path(__file__).resolve().parents[1] / "scripts/golden_reset.py")
golden = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(golden)


class Rows:
    def __init__(self, value): self.value = value
    def fetchone(self): return self.value


class Catalogue:
    def __init__(self):
        self.databases = {golden.TARGET: (10, True, None)}
        self.statements = []
        self.version, self.tls, self.lock = 180004, True, True
        self.fail_create_live = False
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, query, parameters=()):
        query = query if isinstance(query, str) else query.as_string()
        self.statements.append((query, parameters))
        if "pg_control_system()" in query: return Rows((self.version, self.tls, "fixture-system"))
        if "pg_try_advisory_lock" in query: return Rows((self.lock,))
        if "pg_db_role_setting" in query: return Rows((0,))
        if query.startswith("SELECT oid,datallowconn"):
            return Rows(self.databases.get(parameters[0]))
        if query.startswith("SELECT oid FROM pg_database"):
            value = self.databases.get(parameters[0])
            return Rows(None if value is None else (value[0],))
        if query.startswith("CREATE DATABASE"):
            name = re.findall(r'"([^"]+)"', query)[0]
            if name == golden.TARGET and self.fail_create_live: raise RuntimeError("invented failure")
            assert name in {golden.TARGET, golden.GOLDEN}
            self.databases[name] = (30 if name == golden.TARGET else 20, False, None)
        if query.startswith("DROP DATABASE"):
            assert query == 'DROP DATABASE "protected_734"'
            del self.databases[golden.TARGET]
        if query.startswith("ALTER DATABASE"):
            oid, _, marker = self.databases[golden.TARGET]
            self.databases[golden.TARGET] = (oid, query.endswith("true"), marker)
        if query.startswith("COMMENT ON DATABASE"):
            oid, allow, _ = self.databases[golden.GOLDEN]
            self.databases[golden.GOLDEN] = (oid, allow, query.split(" IS '")[1][:-1])
        return Rows((True,))


@pytest.fixture
def fake_vm(monkeypatch, tmp_path):
    catalogue, actions, smoke_calls = Catalogue(), [], []
    monkeypatch.setattr(golden, "service_guard", lambda: None)
    monkeypatch.setattr(golden, "database_parameters", lambda *a, **kw: {"host": "127.0.0.1", "port": 5433})
    monkeypatch.setattr(golden.psycopg, "connect", lambda **kw: catalogue)
    monkeypatch.setattr(golden, "database_state", lambda root: {"members": 734})
    monkeypatch.setattr(golden, "control_app", actions.append)
    monkeypatch.setattr(golden, "export_audit", lambda root, directory: {"metadata_only": True, "events": 3})
    monkeypatch.setattr(golden, "smoke", lambda: smoke_calls.append(True) or {"passed": True})
    monkeypatch.setattr(golden, "wait_and_smoke", lambda: {"passed": True})
    return SimpleNamespace(catalogue=catalogue, actions=actions, smoke_calls=smoke_calls,
                           root=tmp_path / "module-a", private=tmp_path / "pentest")


def test_create_immutable_template_and_reset_once(fake_vm):
    vm = fake_vm
    created = golden.operate("create", vm.root, vm.private)
    assert created["passed"] and vm.actions == ["stop", "start"]
    assert vm.catalogue.databases[golden.GOLDEN][1] is False
    old_bytes = (vm.private / "golden-template.json").read_bytes()
    again = golden.operate("create", vm.root, vm.private)
    assert again["existing_preserved"] and (vm.private / "golden-template.json").read_bytes() == old_bytes
    assert not any(query.startswith("DROP DATABASE") for query, _ in vm.catalogue.statements)
    vm.smoke_calls.clear()
    reset = golden.operate("reset", vm.root, vm.private)
    assert reset["passed"] and reset["members"] == 734
    assert vm.smoke_calls == []  # damaged pentest app must still be resettable
    assert vm.actions == ["stop", "start", "stop", "start"]
    assert vm.catalogue.databases[golden.TARGET][0] == 30
    document = golden.read_private(vm.private / "golden-template.json")
    assert document["live_oid"] == 30 and document["golden_oid"] == 20
    assert sum(query.startswith("DROP DATABASE") for query, _ in vm.catalogue.statements) == 1


@pytest.mark.parametrize("change", ["live_oid", "golden_oid", "marker", "system", "target", "allowed_connections"])
def test_changed_identity_refuses_drop(fake_vm, change):
    vm = fake_vm
    golden.operate("create", vm.root, vm.private)
    path = vm.private / "golden-template.json"
    metadata = golden.read_private(path)
    if change == "allowed_connections":
        oid, _, marker = vm.catalogue.databases[golden.GOLDEN]
        vm.catalogue.databases[golden.GOLDEN] = (oid, True, marker)
    else:
        field = "system_identifier" if change == "system" else change
        metadata[field] = "unrelated" if field in {"marker", "system_identifier", "target"} else 999
        golden.save_metadata(path, metadata, replace=True)
    with pytest.raises(ValueError): golden.operate("reset", vm.root, vm.private)
    assert not any(query.startswith("DROP DATABASE") for query, _ in vm.catalogue.statements)
    assert vm.actions == ["stop", "start"]


@pytest.mark.parametrize("issue", ["version", "tls", "lock", "missing_live", "unsafe_host"])
def test_wrong_cluster_preflight_has_no_stop_or_drop(fake_vm, monkeypatch, issue):
    vm = fake_vm
    if issue == "version": vm.catalogue.version = 170000
    if issue == "tls": vm.catalogue.tls = False
    if issue == "lock": vm.catalogue.lock = False
    if issue == "missing_live": vm.catalogue.databases.clear()
    if issue == "unsafe_host": monkeypatch.setattr(golden, "database_parameters", lambda *a, **kw: {"host": "other.example.test", "port": 5433})
    with pytest.raises(ValueError): golden.operate("create", vm.root, vm.private)
    assert vm.actions == []
    assert not any(query.startswith("DROP DATABASE") for query, _ in vm.catalogue.statements)


def test_failed_app_does_not_freeze_a_bad_golden(fake_vm, monkeypatch):
    monkeypatch.setattr(golden, "smoke", lambda: {"passed": False})
    with pytest.raises(ValueError): golden.operate("create", fake_vm.root, fake_vm.private)
    assert fake_vm.actions == [] and golden.GOLDEN not in fake_vm.catalogue.databases


def test_reset_failure_never_starts_app_with_missing_database(fake_vm):
    vm = fake_vm
    golden.operate("create", vm.root, vm.private)
    vm.catalogue.fail_create_live = True
    with pytest.raises(RuntimeError): golden.operate("reset", vm.root, vm.private)
    assert vm.actions == ["stop", "start", "stop"]
    assert golden.GOLDEN in vm.catalogue.databases


def test_service_guard_and_control_are_narrow(monkeypatch):
    with pytest.raises(ValueError): golden.service_guard()  # Windows test checkout is not the VM
    commands = []
    monkeypatch.setattr(golden, "run_command", lambda args: commands.append(args))
    golden.control_app("stop")
    assert commands == [["sudo", "-n", "systemctl", "stop", "dpr-web.service", "dpr-api.service"]]
    with pytest.raises(ValueError): golden.control_app("stop-all")


def test_run_command_does_not_echo_failed_process_output(monkeypatch):
    monkeypatch.setattr(golden.subprocess, "run", lambda *a, **kw: SimpleNamespace(stdout="active\n"))
    assert golden.run_command(["systemctl", "is-active", "dpr-api.service"]) == "active"


def test_audit_export_sanitizes_unexpected_values():
    canary = "invented-private-value-do-not-export"
    row = {"event_id": 1, "occurred_at": datetime.now(timezone.utc), "actor": str(uuid4()),
           "anggota_id": str(uuid4()), "request_id": None, "action": "detail", "actor_role": "operator",
           "database_user": "app_user", "effective_role": "app_user", "field_class": "PII", "decision": "allowed",
           "email": canary}
    assert canary not in json.dumps(golden.safe_audit_row(row))
    for field in ("actor", "anggota_id", "action", "actor_role", "database_user", "field_class", "decision"):
        row[field] = canary
    assert canary not in json.dumps(golden.safe_audit_row(row))


def test_audit_stream_is_private_metadata_only(tmp_path, monkeypatch):
    row = {"event_id": 1, "occurred_at": datetime.now(timezone.utc), "actor": None, "anggota_id": None,
           "request_id": None, "action": "login", "actor_role": "operator", "database_user": "app_user",
           "effective_role": "app_user", "field_class": "AUTH", "decision": "allowed"}
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def execute(self, query): assert "SELECT event_id" in query and "password" not in query
        def __iter__(self): return iter([row])
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def cursor(self, **kwargs): return Cursor()
    monkeypatch.setattr(golden, "database_parameters", lambda *a, **kw: {})
    monkeypatch.setattr(golden.psycopg, "connect", lambda **kw: Connection())
    result = golden.export_audit(tmp_path, tmp_path / "exports")
    assert result["events"] == 1 and result["metadata_only"]
    assert json.loads(Path(result["path"]).read_text())["action"] == "login"


def test_main_requires_explicit_reset_confirmation(tmp_path):
    output = tmp_path / "refusal.json"
    assert golden.main(["reset", "--evidence", str(output)]) == 1
    result = json.loads(output.read_text())
    assert result["passed"] is False and result["reset_test_status"] == "NOT TESTED"


def test_database_state_checks_count_acl_and_owner(monkeypatch, tmp_path):
    class Connection:
        count = 734
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def execute(self, query):
            return Rows((self.count,)) if "count(*)" in query else Rows(("schema_owner", True))
    connection = Connection()
    monkeypatch.setattr(golden, "database_parameters", lambda *a, **kw: {})
    monkeypatch.setattr(golden.psycopg, "connect", lambda **kw: connection)
    monkeypatch.setattr(golden, "security_checks", lambda db: {"A5": True})
    assert golden.database_state(tmp_path)["members"] == 734
    connection.count = 735
    with pytest.raises(ValueError): golden.database_state(tmp_path)


@pytest.mark.parametrize("ready", [True, False])
def test_waiter_smokes_only_after_ready_once(monkeypatch, ready):
    import httpx
    import ssl
    checks = []
    monkeypatch.setenv("NODE_EXTRA_CA_CERTS", "fixture-only")
    monkeypatch.setattr(ssl, "create_default_context", lambda **kw: object())
    monkeypatch.setattr(golden.time, "sleep", lambda seconds: None)
    class Client:
        def __init__(self, **kwargs): assert kwargs["trust_env"] is False
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def get(self, url):
            assert url == "https://127.0.0.1:3443/api/health/ready"
            return SimpleNamespace(status_code=200 if ready else 503)
    monkeypatch.setattr(httpx, "Client", Client)
    monkeypatch.setattr(golden, "smoke", lambda: checks.append(True) or {"passed": True})
    assert golden.wait_and_smoke()["passed"] is ready
    assert checks == ([True] if ready else [])


@pytest.mark.parametrize("failure", [False, True])
def test_main_reports_actual_reset_result_and_hides_errors(tmp_path, monkeypatch, failure, capsys):
    monkeypatch.setattr(golden.Settings, "from_env", lambda: object())
    monkeypatch.setattr(golden, "setup_url", lambda *args: None)
    monkeypatch.setenv("APP_SETUP_DATABASE_URL", "fixture-not-printed")
    monkeypatch.setenv("DPR_SECRETS_DIR", str(tmp_path / "module-a"))
    monkeypatch.setenv("DPR_PRIVATE_DIR", str(tmp_path / "private"))
    if failure:
        monkeypatch.setattr(golden, "operate", lambda *a: (_ for _ in ()).throw(RuntimeError("private-canary")))
    else:
        monkeypatch.setattr(golden, "operate", lambda *a: {"passed": True, "members": 734})
    path = tmp_path / "reset.json"
    assert golden.main(["reset", "--confirm-target", "protected_734", "--evidence", str(path)]) == int(failure)
    result = json.loads(path.read_text())
    assert result["reset_test_status"] == ("FAILED" if failure else "PASSED")
    assert "private-canary" not in path.read_text() + capsys.readouterr().out


def test_nondefault_database_settings_refuse_template_before_stop(fake_vm):
    original = fake_vm.catalogue.execute
    def execute(query, parameters=()):
        return Rows((1,)) if isinstance(query, str) and "pg_db_role_setting" in query else original(query, parameters)
    fake_vm.catalogue.execute = execute
    with pytest.raises(ValueError): golden.operate("create", fake_vm.root, fake_vm.private)
    assert not fake_vm.actions
