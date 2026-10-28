import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

from scripts.backup import cli, runner
from scripts.backup.crypto import BackupError, canonical, key_id, sign_manifest
from scripts.backup.postgres import TABLES, SERVICE_TABLES


def test_parser_requires_safe_options():
    with pytest.raises(SystemExit): cli.parser().parse_args(["backup", "--source", "postgres"])
    with pytest.raises(SystemExit): cli.parser().parse_args(["backup", "--source", "protected_734", "--password", "forbidden"])
    assert cli.parser().parse_args(["restore", "--manifest", "synthetic"]).with_openbao is False


@pytest.mark.parametrize("command", ["init-keys", "backup", "restore", "tamper-test", "retention-test"])
def test_cli_writes_machine_reports_without_secrets(tmp_path, monkeypatch, capsys, command):
    secret = os.urandom(32).hex(); keys = (os.urandom(32), os.urandom(32))
    monkeypatch.setenv("DPR_SECRETS_DIR", str(tmp_path / "secrets"))
    monkeypatch.setattr(cli, "local_keys", lambda *a, **kw: keys)
    monkeypatch.setattr(cli, "backup_keys", lambda: keys)
    monkeypatch.setattr(cli, "parameters", lambda *a, **kw: {"password": secret})
    monkeypatch.setattr(cli, "artifact_store", lambda path: Path(path))
    for name in ("backup", "restore", "tamper_test", "retention_test"):
        monkeypatch.setattr(cli, name, lambda *a, **kw: {"passed": True, "source_rows": 17})
    args = ["--local-credentials", "--evidence-dir", str(tmp_path / "evidence"), command]
    if command == "backup": args += ["--source", "protected_1m", "--output-dir", str(tmp_path / "archives")]
    elif command != "init-keys": args += ["--manifest", str(tmp_path / "synthetic.manifest.json")]
    if command == "retention-test": args += ["--output-dir", str(tmp_path / "archives")]
    assert cli.main(args) == 0
    evidence = list((tmp_path / "evidence").glob("*.json"))
    assert len(evidence) == 1 and json.loads(evidence[0].read_text())["passed"]
    assert secret not in evidence[0].read_text()+capsys.readouterr().out


def test_cli_failure_redacts_arbitrary_errors(tmp_path, monkeypatch, capsys):
    secret = os.urandom(32).hex()
    monkeypatch.setattr(cli, "backup_keys", lambda: (_ for _ in ()).throw(RuntimeError(secret)))
    assert cli.main(["--evidence-dir", str(tmp_path), "restore", "--manifest", "synthetic"]) == 1
    report = (tmp_path / "restore-report.json").read_text()
    assert secret not in report+capsys.readouterr().out and not json.loads(report)["passed"]
    monkeypatch.setattr(cli, "backup_keys", lambda: (_ for _ in ()).throw(BackupError("invalid_manifest")))
    assert cli.main(["--evidence-dir", str(tmp_path), "restore", "--manifest", "synthetic"]) == 1
    assert json.loads((tmp_path/"restore-report.json").read_text())["error"] == "invalid_manifest"


@pytest.mark.parametrize("tables", [TABLES, SERVICE_TABLES])
def test_manifest_validation_schema_and_hmac(tmp_path, tables):
    keys = (os.urandom(32), os.urandom(32)); identity = str(uuid4())
    path = tmp_path/(identity+".manifest.json")
    counts = {table: 0 for table in tables}
    payload = {"format_version": 1, "artifact_id": identity, "postgres_major": 18,
        "encryption": "AES-256-GCM-framed-HKDF-SHA256-v1", "dump_role": "backup_user", "snapshot_consistent": True,
        "encryption_key_id": key_id(keys[0]), "manifest_key_id": key_id(keys[1]), "size_bytes": 100,
        "sha256": "0"*64, "table_rows": counts, "source_rows": 0, "source_database": "protected_1m",
        "created_at": "2026-10-27T00:00:00+00:00", "retention_deadline": "2026-11-27T00:00:00+00:00"}
    path.write_bytes(canonical(sign_manifest(payload, keys[1])))
    assert runner.inspect_manifest(path, keys) == payload
    for names in ((*TABLES, "service_sessions"), (*SERVICE_TABLES, "unreviewed")):
        path.write_bytes(canonical(sign_manifest({**payload, "table_rows": dict.fromkeys(names, 0)}, keys[1])))
        with pytest.raises(BackupError): runner.inspect_manifest(path, keys)
    for field, value in [("artifact_id", "../unsafe"), ("format_version", 2), ("size_bytes", -1), ("table_rows", {}),
                         ("sha256", "bad"), ("source_database", "postgres"), ("source_rows", 1),
                         ("created_at", "2026-10-27"), ("retention_deadline", "2026-10-27T00:00:00+00:00")]:
        path.write_bytes(canonical(sign_manifest({**payload, field: value}, keys[1])))
        with pytest.raises(BackupError): runner.inspect_manifest(path, keys)
    path.write_text("x"*65537)
    with pytest.raises(BackupError): runner.inspect_manifest(path, keys)
    runner.source_allowed("protected_1m")
    with pytest.raises(BackupError): runner.source_allowed("postgres")
