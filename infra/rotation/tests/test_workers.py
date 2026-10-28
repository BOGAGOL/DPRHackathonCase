import base64
import io
import json
import os
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest

from infra.rotation import worker, runner
from infra.rotation.worker import RotationError


def test_environment_separates_credentials(monkeypatch):
    for name in ("OPENBAO_ADDR", "OPENBAO_CACERT", "OPENBAO_KEY_OPERATOR_TOKEN", "OPENBAO_VALIDATION_TOKEN",
                 "PGPASSWORD", "PGUSER", "DPR_ROTATION_BOOTSTRAP_PASSWORD", "DPR_SECRETS_DIR", "OPENBAO_TOKEN"):
        monkeypatch.setenv(name, os.urandom(24).hex())
    reader = {"host": "127.0.0.1", "port": 5433, "user": "scanner_user", "password": os.urandom(24).hex(), "sslrootcert": "public-ca"}
    operator = runner.worker_environment("operator")
    validator = runner.worker_environment("validator", reader)
    assert not any(name in operator for name in ("PGPASSWORD", "PGUSER", "DPR_SECRETS_DIR", "OPENBAO_VALIDATION_TOKEN", "OPENBAO_TOKEN"))
    assert validator["PGPASSWORD"] == reader["password"] and "OPENBAO_KEY_OPERATOR_TOKEN" not in validator
    assert "DPR_ROTATION_BOOTSTRAP_PASSWORD" not in operator and "DPR_ROTATION_BOOTSTRAP_PASSWORD" not in validator
    with pytest.raises(RotationError): runner.worker_environment("invalid")


def test_private_serialization():
    identity = uuid4()
    values = {"id": identity, "ct": b"synthetic", "date": date(2000, 1, 1), "timestamp": datetime.now(timezone.utc)}
    result = json.loads(worker.encoded(values))
    assert result["id"] == str(identity) and result["ct"]["bytes"] == base64.b64encode(values["ct"]).decode()
    with pytest.raises(TypeError): worker.json_value(object())


def test_operator_dispatch_never_decrypts():
    from types import SimpleNamespace
    client = SimpleNamespace(key_metadata=lambda kek: {"latest_version": 1}, rotate_key=lambda kek: {"latest_version": 2}, rewrap_batch=lambda kek, wrapped, key_version: wrapped)
    assert worker.operate(client, {"action": "metadata"})["latest_version"] == 1
    assert worker.operate(client, {"action": "rotate"})["latest_version"] == 2
    assert worker.operate(client, {"action": "rewrap", "wrapped": [], "version": 2}) == []
    with pytest.raises(RotationError): worker.operate(client, {"action": "decrypt"})


def test_validator_keeps_plaintext_and_dek_comparisons_private(monkeypatch):
    original_scan = worker.scan
    snapshot = {"rows": 17, "fields": 410, "opaque": os.urandom(32), "plaintext": os.urandom(32), "deks": os.urandom(32)}
    monkeypatch.setattr(worker, "scan", lambda *a, **kw: dict(snapshot))
    validator = worker.Validator(None)
    assert validator.request({"action": "before", "database": "protected_734"})["rows"] == 17
    with pytest.raises(RotationError): validator.request({"action": "before", "database": "protected_734"})
    assert validator.request({"action": "after", "database": "protected_734"})["all_record_deks_unchanged"]
    assert "plaintext" not in validator.request({"action": "before", "database": "protected_734"})
    snapshot["opaque"] = os.urandom(32)
    with pytest.raises(RotationError): validator.request({"action": "after", "database": "protected_734"})
    with pytest.raises(RotationError): validator.request({"action": "bad", "database": "protected_734"})
    with pytest.raises(RotationError): original_scan("postgres", None, os.urandom(32))


def test_worker_protocol_redacts_errors_and_progress(monkeypatch):
    from types import SimpleNamespace
    client = SimpleNamespace(require_policy=lambda value: None)
    client.__enter__ = lambda: client
    class Context:
        def __enter__(self): return client
        def __exit__(self, *_): pass
    monkeypatch.setattr(worker, "OpenBaoClient", lambda **kw: Context())
    for name in ("PGUSER", "PGPASSWORD", "OPENBAO_VALIDATION_TOKEN", "OPENBAO_KEY_OPERATOR_TOKEN"): monkeypatch.delenv(name, raising=False)
    secret = os.urandom(24).hex()
    def action(client, message):
        if message["action"] == "bad": raise RuntimeError(secret)
        return {"latest_version": 2}
    monkeypatch.setattr(worker, "operate", action)
    output = io.StringIO(); worker.serve("operator", io.StringIO('{"action":"metadata"}\n{"action":"bad"}\n'), output)
    lines = [json.loads(line) for line in output.getvalue().splitlines()]
    assert lines[0]["ok"] and not lines[1]["ok"] and secret not in output.getvalue()
    monkeypatch.setenv("PGUSER", "backup_user")
    with pytest.raises(RotationError): worker.serve("operator", io.StringIO(), io.StringIO())
    monkeypatch.delenv("PGUSER"); monkeypatch.setenv("OPENBAO_KEY_OPERATOR_TOKEN", secret)
    with pytest.raises(RotationError): worker.serve("validator", io.StringIO(), io.StringIO())
    with pytest.raises(RotationError): worker.serve("bad", io.StringIO(), io.StringIO())
    monkeypatch.delenv("OPENBAO_KEY_OPERATOR_TOKEN")
    class FakeValidator:
        def __init__(self, client): pass
        def request(self, message, *, progress):
            progress(10000)
            return {"rows": 10000}
    monkeypatch.setattr(worker, "Validator", FakeValidator)
    output = io.StringIO(); worker.serve("validator", io.StringIO('{"action":"before"}\n'), output)
    assert json.loads(output.getvalue().splitlines()[0])["progress_rows"] == 10000


def test_worker_pipe_protocol_and_cleanup(monkeypatch):
    from types import SimpleNamespace
    child = SimpleNamespace(stdin=io.StringIO(), stdout=io.StringIO('{"progress_rows":10000}\n{"ok":true,"result":17}\n'), wait=lambda timeout: 0)
    monkeypatch.setattr(runner, "worker_environment", lambda *a: {})
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **kw: child)
    with runner.Worker("operator") as process:
        assert process.request({"action": "metadata"}) == 17
        child.stdout = io.StringIO('{"ok":false}\n')
        with pytest.raises(RotationError): process.request({"action": "rotate"})
        child.stdout = io.StringIO('invalid\n')
        with pytest.raises(RotationError): process.request({"action": "rotate"})
        child.stdout = io.StringIO('')
        with pytest.raises(RotationError): process.request({"action": "rotate"})
    assert child.stdin.closed and child.stdout.closed
