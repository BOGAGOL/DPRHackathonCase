import json
import os
from pathlib import Path
import secrets
import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import quote

import pytest

from datagen import database as db
from datagen.model import checksum, generate


@pytest.fixture
def environment(monkeypatch, tmp_path):
    secret = secrets.token_urlsafe(32)
    monkeypatch.setenv("DATAGEN_DATABASE_URL", "postgresql://postgres:" + quote(secret) + "@127.0.0.1:5433/postgres")
    monkeypatch.setenv("BENCH_DATABASE_URL", "postgresql://bench_user:" + quote(secret) + "@127.0.0.1:5433/baseline_test")
    monkeypatch.setenv("DPR_PRIVATE_DIR", str(tmp_path / "private"))
    monkeypatch.setattr(db, "ROOT", tmp_path / "repository")
    return tmp_path


def connection():
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.info.server_version = 180006
    return conn


def test_guard_and_env_never_redirect_to_source(environment, monkeypatch):
    for name in ("postgres", "protected_100k", "baseline_x;drop", "baseline_../x", "BASELINE_X"):
        with pytest.raises(ValueError):
            db.guard_target(name)
    assert db.guard_target("baseline_100k") == "baseline_100k"
    assert db.parameters("baseline_test")["dbname"] == "baseline_test"
    monkeypatch.setenv("DATAGEN_DATABASE_URL", "postgresql://localhost:9999/postgres")
    with pytest.raises(ValueError):
        db.parameters("postgres")
    monkeypatch.delenv("DATAGEN_DATABASE_URL")
    with pytest.raises(ValueError):
        db.parameters("postgres")


def test_source_read_only_version_count_guard(environment, monkeypatch, source):
    conn = connection()
    conn.execute.return_value.fetchall.return_value = list(generate(source, 734))
    monkeypatch.setattr(db.psycopg, "connect", MagicMock(return_value=conn))
    assert len(db.source_rows()) == 734
    assert "READ ONLY" in conn.execute.call_args_list[0].args[0]
    assert all("INSERT" not in str(c) and "CREATE" not in str(c) for c in conn.execute.call_args_list)
    conn.info.server_version = 170000
    with pytest.raises(ValueError):
        db.source_rows()
    conn.info.server_version = 180006
    conn.execute.return_value.fetchall.return_value = source
    with pytest.raises(ValueError):
        db.source_rows()


def test_record_and_target_commit_provenance(environment, monkeypatch):
    db.record("baseline_test", {"status": "PASSED", "count": 40})
    assert json.loads((db.ROOT / "evidence/datasets/baseline_test.json").read_text())["count"] == 40
    assert (db.ROOT / "results/bench/datasets/baseline_test.json").exists()
    path = db.ROOT / "evidence/targets_commit.json"
    path.write_text(json.dumps({"commit": "a" * 40, "file": "docs/targets.md", "committed_at_wib": "2026-10-26T23:07:44+07:00"}))
    run = MagicMock(side_effect=[SimpleNamespace(stdout=""), SimpleNamespace(stdout="b" * 40 + "\n"), SimpleNamespace(stdout="?? datagen/\n")])
    monkeypatch.setattr(db.subprocess, "run", run)
    assert db.provenance()["datagen_worktree_dirty"]
    path.write_text(json.dumps({"commit": "invalid", "file": "docs/targets.md"}))
    with pytest.raises(ValueError):
        db.provenance()


def test_validate_streams_all_rows_in_read_only_snapshot(environment, monkeypatch, source):
    conn = connection()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.__iter__.return_value = iter(generate(source, 200))
    monkeypatch.setattr(db, "source_rows", lambda: source)
    monkeypatch.setattr(db.psycopg, "connect", MagicMock(return_value=conn))
    assert db.validate_database("baseline_test", 200)["passed"]
    assert "READ ONLY" in conn.execute.call_args.args[0]
    assert conn.cursor.call_args.kwargs["name"] == "datagen_validation"


def test_build_new_database_only_and_persists_failures(environment, monkeypatch, source):
    monkeypatch.setattr(db, "source_rows", lambda: source)
    monkeypatch.setattr(db, "provenance", lambda: {"targets_commit": "a" * 40})
    admin, target = connection(), connection()
    admin.execute.return_value.fetchone.return_value = None
    monkeypatch.setattr(db.psycopg, "connect", MagicMock(side_effect=[admin, target]))
    schema = db.ROOT / "sql/baseline/01_schema.sql"
    schema.parent.mkdir(parents=True)
    schema.write_text("CREATE TABLE test (id bigint)")
    copy = target.cursor.return_value.copy.return_value.__enter__.return_value
    monkeypatch.setattr(db, "validate_database", lambda *a: {"passed": True, "checksum_sha256": "aggregate"})
    result = db.build("baseline_test", 200)
    assert result["validation"]["source_database_unchanged"]
    assert copy.write_row.call_count == 200
    assert all("DROP DATABASE" not in str(c) for c in admin.execute.call_args_list)
    # Existing target must fail before opening it, even if it contains a partial previous run.
    admin.execute.return_value.fetchone.return_value = (1,)
    connect = MagicMock(return_value=admin)
    monkeypatch.setattr(db.psycopg, "connect", connect)
    with pytest.raises(ValueError, match="exists"):
        db.build("baseline_test", 200)
    assert connect.call_count == 1
    with pytest.raises(ValueError, match="smaller"):
        db.build("baseline_test", 1)
    admin.execute.return_value.fetchone.return_value = None
    target.execute.side_effect = RuntimeError("driver details withheld")
    monkeypatch.setattr(db.psycopg, "connect", MagicMock(side_effect=[admin, target]))
    with pytest.raises(RuntimeError):
        db.build("baseline_test", 200)
    assert json.loads((db.ROOT / "evidence/datasets/baseline_test.json").read_text())["status"] == "FAILED"


def test_private_path_guard(environment, monkeypatch):
    with pytest.raises(ValueError):
        db.private_path(db.ROOT / "unsafe.dump")
    monkeypatch.setenv("DPR_PRIVATE_DIR", str(db.ROOT / "private"))
    with pytest.raises(ValueError):
        db.private_path(db.ROOT / "private/snapshot.dump")
    monkeypatch.delenv("DPR_PRIVATE_DIR")
    with pytest.raises(ValueError):
        db.private_path(environment / "private/snapshot.dump")


def test_snapshot_binary_stream_no_secret_arguments_or_overwrite(environment, monkeypatch):
    db.record("baseline_test", {"database": "baseline_test", "validation": {"passed": True}})
    out = environment / "private/snapshot.dump"
    def dump(command, **kwargs):
        assert not any("password" in arg.lower() for arg in command)
        kwargs["stdout"].write(b"PGDMP\x00\xff\r\n")
    monkeypatch.setattr(db.subprocess, "run", dump)
    report = db.snapshot("baseline_test", out)
    assert report["bytes"] == 9 and report["outside_repository"]
    with pytest.raises(FileExistsError):
        db.snapshot("baseline_test", out)
    failing = environment / "private/failing.dump"
    monkeypatch.setattr(db.subprocess, "run", MagicMock(side_effect=subprocess.CalledProcessError(1, "docker")))
    with pytest.raises(subprocess.CalledProcessError):
        db.snapshot("baseline_test", failing)
    assert not failing.exists() and out.exists()


def test_provision_uses_scram_and_keeps_source_read_only(environment, monkeypatch):
    db.record("baseline_test", {"database": "baseline_test"})
    admin, bench, scanner_check, original = (connection() for _ in range(4))
    admin.execute.return_value.fetchone.side_effect = [None, (1,), (0,)]
    admin.pgconn.encrypt_password.return_value = secrets.token_bytes(24).hex().encode()
    bench.execute.return_value.fetchone.side_effect = [("bench_user",), (200,), (False,), (False,)]
    scanner_check.execute.return_value.fetchone.side_effect = [(True,), (False,), (False,), (False,), (False,)]
    original.execute.return_value.fetchone.return_value = (False,)
    monkeypatch.setattr(db.psycopg, "connect", MagicMock(side_effect=[admin, bench, scanner_check, original]))
    result = db.provision("baseline_test")
    assert result["passed"]
    assert admin.pgconn.encrypt_password.call_args.args[-1] == b"scram-sha-256"
    assert "READ ONLY" in original.execute.call_args_list[0].args[0]
    assert all("GRANT" not in str(c) and "REVOKE" not in str(c) for c in original.execute.call_args_list)


def test_provision_rejects_unsafe_existing_role(environment, monkeypatch):
    conn = connection()
    conn.execute.return_value.fetchone.return_value = (True, False, False, False, False)
    monkeypatch.setattr(db.psycopg, "connect", MagicMock(return_value=conn))
    with pytest.raises(ValueError, match="unsafe"):
        db.provision("baseline_test")
