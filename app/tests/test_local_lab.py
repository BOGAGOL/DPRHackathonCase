"""Guard persistent lab custody, minimal runtime secrets and bounded write recovery."""
import importlib.util
import json
from pathlib import Path
import secrets
import subprocess

import pytest


def lab():
    path = Path(__file__).resolve().parents[1] / "scripts/local_lab.py"
    spec = importlib.util.spec_from_file_location("local_lab_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def state(module):
    return {"owner": module.OWNER, "passwords": {role: secrets.token_urlsafe(24) for role in ("postgres", *module.ROLES)}}


def test_inspect_refuses_unrelated_pg_dpr_before_mutation(monkeypatch):
    module = lab()
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, json.dumps([{"Config": {"Labels": {"dpr.owner": "other"}}}]), ""))
    with pytest.raises(ValueError, match="not owned"):
        module.inspect_owned()


def test_inspect_accepts_only_our_exact_ownership_labels(monkeypatch):
    module = lab()
    labels = {"dpr.owner": module.OWNER, "com.docker.compose.project": "dpr-zhafif-local"}
    value = {"Config": {"Labels": labels}}
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, json.dumps([value]), ""))
    assert module.inspect_owned() == value
    labels["com.docker.compose.project"] = "other"
    with pytest.raises(ValueError):
        module.inspect_owned()


def test_docker_permission_failure_cannot_masquerade_as_absent_container(monkeypatch):
    module = lab()
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "permission denied"))
    monkeypatch.setattr(module, "command", lambda *a, **k: "18")
    with pytest.raises(RuntimeError, match="safely inspect"):
        module.inspect_owned()


def test_missing_container_is_checked_against_live_daemon(monkeypatch):
    module = lab()
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "Error: No such container: pg-dpr"))
    calls = []
    monkeypatch.setattr(module, "command", lambda args, **k: calls.append(args) or "18")
    assert module.inspect_owned() is None
    assert calls[0][:2] == ["docker", "info"]


@pytest.mark.parametrize("ref", ["main; echo bad", "HEAD", "-h", "origin/other", "A" * 40, "a" * 40 + "\n"])
def test_dataset_ref_rejects_unreviewed_or_shelllike_input(ref):
    with pytest.raises(ValueError):
        lab().source_payload(ref)


def test_dataset_payload_requires_exact_734_inserts(monkeypatch):
    module = lab()
    outputs = iter(["a" * 40, "INSERT INTO anggota VALUES (NULL);\n" * 733])
    monkeypatch.setattr(module, "command", lambda *a, **k: next(outputs))
    with pytest.raises(ValueError, match="734"):
        module.source_payload("origin/main")


def test_runtime_environment_excludes_admin_other_secrets_and_bypass(monkeypatch, tmp_path):
    module = lab()
    value = state(module)
    canary = secrets.token_urlsafe(24)
    for key in ("APP_SETUP_DATABASE_URL", "OPENBAO_TOKEN", "MY_PASSWORD", "DPR_PRIVATE_DIR", "SECRET_KEY"):
        monkeypatch.setenv(key, canary)
    monkeypatch.setenv("DPR_ALLOW_DISPOSABLE_DATABASE", "1")
    env = module.environment(tmp_path, value)
    assert canary not in json.dumps(env)
    assert value["passwords"]["postgres"] not in json.dumps(env)
    assert "DPR_ALLOW_DISPOSABLE_DATABASE" not in env
    assert env["MODE"] == "plain" and env["APP_ORIGIN"].startswith("https://")
    for name, role in [("DATABASE_URL", "app_user"), ("ANALYST_DATABASE_URL", "analyst_user"), ("AUDITOR_DATABASE_URL", "auditor_user")]:
        from sqlalchemy.engine import make_url
        url = make_url(env[name])
        assert url.username == role and url.database == "baseline_100k"
        assert url.query["sslmode"] == "verify-full"


@pytest.mark.parametrize("role,database", [("root", "baseline_100k"), ("app_user", "protected_100k"), ("postgres", "other")])
def test_local_url_cannot_target_arbitrary_database(role, database, tmp_path):
    module = lab()
    with pytest.raises(ValueError):
        module.db_url(tmp_path, state(module), role, database)


def test_private_state_rejects_missing_identities_and_foreign_owner(tmp_path):
    module = lab()
    value = state(module)
    module.save(tmp_path / "state.json", value)
    assert module.load_state(tmp_path) == value
    value["owner"] = "foreign"
    module.save(tmp_path / "state.json", value)
    with pytest.raises(ValueError):
        module.load_state(tmp_path)
    value["owner"] = module.OWNER
    del value["passwords"]["postgres"]
    module.save(tmp_path / "state.json", value)
    with pytest.raises(ValueError):
        module.load_state(tmp_path)


def test_insert_cleanup_refuses_concurrent_or_ambiguous_id(tmp_path):
    module = lab()
    assert module.cleanup_insert({}, tmp_path, None, {}) is None
    with pytest.raises(ValueError, match="concurrent"):
        module.cleanup_insert({}, tmp_path, {"id": 100002}, {})


def test_command_error_never_echoes_driver_or_process_output(monkeypatch):
    module = lab()
    canary = secrets.token_urlsafe(24)
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, canary, canary))
    with pytest.raises(RuntimeError) as result:
        module.command(["example"])
    assert canary not in str(result.value)
