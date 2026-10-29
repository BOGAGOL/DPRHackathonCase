"""Safety/regression tests use only invented values and disposable paths."""
from argparse import Namespace
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from infra.reproduce import bootstrap, stack, workflow
from infra.reproduce.__main__ import main
from scripts.backup.postgres import Tools
from scripts.backup.crypto import BackupError
from infra.protected import apply


def test_environment_drops_secrets_and_restores_on_error(monkeypatch):
    monkeypatch.setenv("OPENBAO_TOKEN", "invented-only-not-a-token")
    original = dict(os.environ)
    with pytest.raises(ValueError), stack.environment({"MODE": "protected"}):
        assert "OPENBAO_TOKEN" not in os.environ
        assert os.environ.get("PATH") == original.get("PATH")
        assert os.environ["MODE"] == "protected"
        raise ValueError()
    assert dict(os.environ) == original
    assert "OPENBAO_TOKEN" not in stack.clean_environment()


def test_random_loopback_port_and_explicit_new_directory(tmp_path):
    assert 0 < stack.free_port() <= 65535
    with pytest.raises(ValueError):
        stack.Stack(tmp_path)
    with pytest.raises(ValueError):
        stack.Stack(tmp_path / "fresh", pg_bin=tmp_path)


def test_stack_ownership_parameters_and_executable_allowlist(tmp_path):
    owned = stack.Stack(tmp_path / "owned", pg_bin=tmp_path, bao_bin=tmp_path / "bao")
    assert owned.project.startswith("dpr-repro-") and owned.container != "pg-dpr"
    assert owned.parameters()["sslmode"] == "verify-full"
    assert "native_bin" not in owned.parameters()
    assert owned.pg_environment()["PGPORT"] == str(owned.pg_port)
    with pytest.raises(ValueError):
        owned.executable("sh")
    executable = tmp_path / ("psql.exe" if os.name == "nt" else "psql")
    executable.touch()
    assert owned.executable("psql") == str(executable)
    owned.project = "pg-dpr"
    with pytest.raises(ValueError):
        owned.compose("down")


def test_command_failure_never_echoes_output(tmp_path, monkeypatch, capsys):
    owned = stack.Stack(tmp_path / "owned")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1, stdout=b"invented-private-output"))
    with pytest.raises(RuntimeError, match="withheld"):
        owned.command(["invented-program"])
    with pytest.raises(RuntimeError, match="withheld"):
        bootstrap.checked(["invented-program"])
    with pytest.raises(RuntimeError, match="withheld"):
        workflow.call(["invented-program"], env={})
    assert "invented-private-output" not in capsys.readouterr().out


def test_stack_cleanup_only_owned_resources(tmp_path, monkeypatch):
    owned = stack.Stack(tmp_path / "owned")
    owned.compose_started = True
    calls = []
    monkeypatch.setattr(owned, "compose", lambda *args: calls.append(args))
    owned.__exit__(None, None, None)
    assert calls == [("down", "--volumes", "--remove-orphans")]
    assert not owned.compose_started


def test_missing_input_writes_failed_new_report_only(tmp_path, monkeypatch):
    monkeypatch.setattr(workflow, "ROOT", tmp_path)
    old = tmp_path / "evidence/historical.json"
    old.parent.mkdir()
    old.write_text('{"untouched":true}')
    assert workflow.run(Namespace(command="verify", data=tmp_path / "absent.sql", native_pg_bin=None, native_bao_bin=None)) == 1
    report = json.loads(next((tmp_path / "evidence/reproduction").glob("*/summary.json")).read_text())
    assert report["passed"] is False and report["failed_stage"] == "preflight"
    assert old.read_text() == '{"untouched":true}'


def test_setup_requirements_are_separate_and_frontend_build_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap, "ROOT", tmp_path)
    monkeypatch.setattr(bootstrap.shutil, "which", lambda name: name)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout="v22.10.0"))
    monkeypatch.setattr(bootstrap.venv.EnvBuilder, "create", lambda self, path: None)
    calls = []
    monkeypatch.setattr(bootstrap, "checked", lambda cmd, **kw: calls.append((cmd, kw)))
    bootstrap.setup()
    runtime = next(cmd for cmd, _ in calls if "infra/requirements.txt" in cmd)
    assessment = next(cmd for cmd, _ in calls if "scanner/requirements.txt" in cmd)
    assert "scanner/requirements.txt" not in runtime and "app/requirements.txt" not in assessment
    assert any(cmd[-2:] == ["run", "build"] for cmd, _ in calls)
    assert json.loads((tmp_path / "evidence/reproduction/generated/setup.json").read_text())["passed"]


def test_setup_rejects_old_node(monkeypatch):
    monkeypatch.setattr(bootstrap.shutil, "which", lambda name: name)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout="v18.20.0"))
    with pytest.raises(ValueError, match="20.9"):
        bootstrap.setup()


def test_test_launcher_checks_all_suites(tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap, "ROOT", tmp_path)
    for name in (".venv", ".venv-assessment"):
        executable = bootstrap.python_bin(tmp_path / name)
        executable.parent.mkdir(parents=True)
        executable.touch()
    calls = []
    monkeypatch.setattr(subprocess, "call", lambda cmd, **kw: calls.append(cmd) or (1 if "app/tests" in cmd else 0))
    assert bootstrap.test() == 1
    assert len(calls) == 3 and "scanner/tests" in calls[2]


def test_cli_setup_and_test_paths(monkeypatch):
    import infra.reproduce.__main__ as cli
    called = []
    monkeypatch.setattr(cli, "setup", lambda: called.append("setup"))
    monkeypatch.setattr(cli, "test", lambda: 3)
    assert main(["setup"]) == 0 and called == ["setup"]
    assert main(["test"]) == 3


def test_native_backup_uses_same_auth_bind_guard(tmp_path, monkeypatch):
    for name in ("psql", "pg_dump", "pg_restore"):
        (tmp_path / (name + (".exe" if os.name == "nt" else ""))).touch()
    monkeypatch.setenv("DPR_BACKUP_NATIVE_PG_BIN", str(tmp_path))
    params = {"host": "127.0.0.1", "port": 12345, "user": "backup_user", "password": "invented-test-only",
              "dbname": "protected_734", "sslrootcert": str(tmp_path / "ca.crt")}
    with Tools("owned-native-reproduction", params) as tools:
        assert tools.environment["PGPORT"] == "12345"
        command = tools.command("pg_dump", ["-Fc"])
        assert command[0].startswith(str(tmp_path)) and "invented-test-only" not in command
        assert tools.environment["PGSSLMODE"] == "verify-full"
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=b"0"))
        with pytest.raises(BackupError, match="do_not_match"):
            tools.bind()
        with pytest.raises(BackupError):
            tools.command("sh", [])


def test_native_provisioning_requires_ca_and_keeps_guards(tmp_path, monkeypatch):
    binary = tmp_path / "psql"
    binary.touch()
    ca = tmp_path / "ca.crt"
    ca.touch()
    profile = apply.load_profile(apply.REPO / "policy/protection_profile.yaml")
    passwords = {role: "invented-test-only-credential" for role in apply.ROLES}
    monkeypatch.setenv("PGSSLMODE", "disable")
    with pytest.raises(ValueError, match="TLS"):
        apply.provision("owned", "protected_734", "dpr_bootstrap", passwords, profile, psql_bin=binary)
    monkeypatch.setenv("PGSSLMODE", "verify-full")
    monkeypatch.setenv("PGSSLROOTCERT", str(ca))
    captured = []
    monkeypatch.setattr(apply.subprocess, "run", lambda cmd, **kw: captured.append((cmd, kw)) or SimpleNamespace(returncode=0))
    apply.provision("owned", "protected_734", "dpr_bootstrap", passwords, profile, psql_bin=binary, system_identifier="1234")
    command, options = captured[0]
    assert command[0] == str(binary)
    assert "Wrong protected target/version" in options["input"] and "1234" in options["input"]
    assert "BEGIN;" in options["input"] and "COMMIT;" in options["input"]
    assert all(value not in command for value in passwords.values())


def test_make_shortcuts_and_compose_are_scoped():
    root = bootstrap.ROOT
    make = (root / "Makefile").read_text()
    for name in ("setup", "demo", "verify", "test"):
        assert f"{name}:\n" in make and f"infra.reproduce {name}" in make
    compose = (root / "infra/reproduce/compose.yaml").read_text()
    assert "127.0.0.1::5432" in compose and "openbao/openbao:2.5.5" in compose
    assert "POSTGRES_PASSWORD_FILE" in compose and "tls_disable" not in compose


@pytest.mark.parametrize("recommendation,minimize", [
    ("generalize_for_analyst", False), ("retain+mask_for_analyst", False), ("review_minimization", True),
])
def test_current_scanner_recommendations_keep_contract_override(recommendation, minimize):
    from policy.build_profile import assessment
    finding = assessment({"confidence": "80", "priority_score": "20", "recommendation": recommendation,
                          "risk_level": "tinggi", "detected_type": "invented", "triage": "review"})
    assert finding["recommendation"] == recommendation
    assert finding["candidate_aead"] is False and finding["candidate_bidx"] is False
    assert finding["minimization_candidate"] == minimize
