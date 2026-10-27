import json
import os

import pytest

from infra.rotation import cli, runner
from infra.rotation.worker import RotationError


def test_cli_reports_success_and_checkpoint_failure(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "runtime_parameters", lambda *a: {})
    monkeypatch.setattr(cli, "prepare", lambda *a: {"passed": True})
    assert cli.main(["--evidence-dir", str(tmp_path), "prepare", "--database", "protected_734"]) == 0
    monkeypatch.setattr(cli, "execute", lambda *a, **kw: {"passed": True, "status": "complete", "target_version": 2})
    args = ["--evidence-dir", str(tmp_path), "rotate", "--database", "protected_734"]
    assert cli.main(args) == 0
    secret = os.urandom(24).hex()
    def fail(*args, **kwargs):
        kwargs["checkpoint"]({"target_version": 3, "passed": False, "status": "rewrapping"})
        raise RuntimeError(secret)
    monkeypatch.setattr(cli, "execute", fail)
    assert cli.main(args) == 1
    report = (tmp_path/"rotation.json").read_text()
    assert json.loads(report)["target_version"] == 3 and secret not in report+capsys.readouterr().out
    with pytest.raises(SystemExit): cli.main(["rotate", "--database", "postgres"])
    with pytest.raises(RotationError): runner.execute(["postgres"], {}, {})
    with pytest.raises(RotationError): runner.execute(["protected_734"], {}, {}, batch_size=101)
    with pytest.raises(RotationError): runner.prepare({"dbname": "postgres"})


def test_runtime_parameters_environment_and_local_dpapi(tmp_path, monkeypatch):
    ca = tmp_path/"ca.crt"; ca.touch(); secret = os.urandom(24).hex()
    monkeypatch.setenv("PGSSLROOTCERT", str(ca)); monkeypatch.setenv("PGPORT", "5433")
    monkeypatch.setenv("DPR_ADMIN_USER_PASSWORD", secret); monkeypatch.setenv("DPR_SCANNER_USER_PASSWORD", secret)
    monkeypatch.setenv("DPR_ROTATION_BOOTSTRAP_PASSWORD", secret)
    for role in ("admin_user", "scanner_user", "bootstrap"):
        assert cli.runtime_parameters("protected_734", role)["password"] == secret
    monkeypatch.setenv("DPR_SECRETS_DIR", str(tmp_path)); monkeypatch.delenv("PGSSLROOTCERT")
    for name in ("DPR_ADMIN_USER_PASSWORD", "DPR_SCANNER_USER_PASSWORD", "DPR_ROTATION_BOOTSTRAP_PASSWORD"): monkeypatch.delenv(name)
    (tmp_path/"postgres/tls").mkdir(parents=True); (tmp_path/"postgres/tls/ca.crt").touch()
    monkeypatch.setattr(cli, "load_password", lambda root: secret)
    monkeypatch.setattr(cli, "role_password", lambda root, role: secret)
    for role in ("admin_user", "scanner_user", "bootstrap"):
        assert cli.runtime_parameters("protected_734", role, True)["password"] == secret
    with pytest.raises(RotationError): cli.runtime_parameters("protected_734", "admin_user")
    with pytest.raises(RotationError): cli.runtime_parameters("protected_734", "bad")
