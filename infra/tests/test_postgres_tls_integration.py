"""Prove TLS reload and rollback in-place on a disposable PG18 data volume."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import subprocess
import time

import pytest
from psycopg import sql

from infra.postgres import enable_tls as pg
from infra.postgres.make_cert import make_certificate
from infra.security import REPO, secure_directory
from infra.tls.make_ca import make_ca


@pytest.mark.skipif(os.environ.get("DPR_POSTGRES_TLS_INTEGRATION") != "1", reason="Set DPR_POSTGRES_TLS_INTEGRATION=1 for disposable in-place TLS/rollback test")
def test_live_enable_reload_verify_and_rollback_preserves_container_and_data(tmp_path, monkeypatch):
    project = "dpr-pg-tls-test-" + secrets.token_hex(5)
    env = {**os.environ, "DPR_POSTGRES_PORT": "0", "DPR_POSTGRES_PASSWORD": secrets.token_urlsafe(32)}
    command = ["docker", "compose", "-p", project, "-f", str(REPO / "infra/tests/compose.postgres.yaml")]
    def compose(*args):
        result = subprocess.run(command + list(args), env=env, capture_output=True, text=True, timeout=180)
        if result.returncode:
            raise RuntimeError("Disposable postgres compose failed; output withheld")
        return result.stdout.strip()
    directory = secure_directory(tmp_path / "secrets")
    make_ca(directory / "tls")
    make_certificate(directory)
    report = {"schema_version": 1, "passed": False, "scope": "disposable PG18; synthetic rows; not pg-dpr", "checks": {}}
    checks = report["checks"]
    try:
        compose("up", "-d", "postgres")
        name = project + "-postgres-1"
        port = int(compose("port", "postgres", "5432").rsplit(":", 1)[1])
        target = pg.ExistingPostgres(name, port=port)
        for _ in range(60):
            try:
                before = target.metadata()
                break
            except pg.TLSUpdateError:
                time.sleep(0.5)
        else:
            raise RuntimeError("Disposable PostgreSQL did not become ready")
        for database in pg.DATABASES:
            target.query('CREATE DATABASE "' + database + '";')
            target.run(["exec", "-i", "--user", "postgres", name, "psql", "-X", "-w", "-v", "ON_ERROR_STOP=1",
                        "-U", "dpr_bootstrap", "-d", database],
                        stdin="CREATE TABLE synthetic_probe (id integer PRIMARY KEY); INSERT INTO synthetic_probe SELECT generate_series(1,5);\n")
        for role in (*pg.BASELINE_ROLES, "app_user"):
            password = secrets.token_urlsafe(32)
            monkeypatch.setenv("DPR_" + role.upper() + "_PASSWORD", password)
            target.query(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {};").format(sql.Identifier(role), sql.Literal(password)).as_string())
        # Simulate an existing installation with the old three-database HBA block.
        original_hba=directory/"postgres/fixture-original-hba.conf"
        target.run(["cp",name+":"+before["hba_file"],str(original_hba)])
        legacy_hba=directory/"postgres/fixture-legacy-hba.conf"
        legacy_hba.write_bytes(pg.LEGACY_HBA_BLOCK.encode()+original_hba.read_bytes())
        # Force a post-reload verification failure: automatic rollback must restore SSL/HBA.
        original_verify = pg.verify_tls
        def fail_verify(*args):
            raise pg.TLSUpdateError("forced_verification_failure")
        monkeypatch.setattr(pg, "verify_tls", fail_verify)
        try:
            target.apply(directory)
            checks["automatic_rollback"] = False
        except pg.TLSUpdateError:
            after_failure = target.metadata()
            checks["automatic_rollback"] = after_failure["settings"] == before["settings"]
        monkeypatch.setattr(pg, "verify_tls", original_verify)
        state_path, result = target.apply(directory)
        checks.update(result["checks"])
        applied_hba=directory/"postgres/fixture-applied-hba.conf"
        target.run(["cp",name+":"+before["hba_file"],str(applied_hba)])
        checks["auth_rules_preserved"]=applied_hba.read_bytes()==pg.baseline_hba_block(result["baseline_client_address"]).encode()+original_hba.read_bytes()
        checks["tls12_or_tls13"] = result["tls_version"] in ("TLSv1.2", "TLSv1.3")
        checks["source_database_catalog_only"] = target.metadata()["database_oids"]["postgres"] == before["database_oids"]["postgres"]
        for database in pg.DATABASES:
            count = target.run(["exec", "--user", "postgres", name, "psql", "-X", "-w", "-Atq", "-U", "dpr_bootstrap",
                                "-d", database, "-c", "SELECT count(*) FROM synthetic_probe;"])
            checks["rows_preserved:" + database] = count == "5"
        mode = target.run(["exec", "--user", "0", name, "stat", "-c", "%a:%U", target.metadata()["settings"]["ssl_key_file"]])
        checks["private_key_postgres_0600"] = mode == "600:postgres"
        # An old managed block represents an installation that already has TLS.
        target.install_file(legacy_hba,before["hba_file"],"600")
        target.query("SELECT pg_reload_conf();")
        upgraded_state, upgraded = target.apply(directory)
        target.run(["cp",name+":"+before["hba_file"],str(applied_hba)])
        checks["legacy_hba_upgraded_without_auth_rule_loss"] = upgraded["passed"] and applied_hba.read_bytes()==pg.baseline_hba_block(result["baseline_client_address"]).encode()+original_hba.read_bytes()
        second_state, second = target.apply(directory)
        checks["repeat_apply_preserves_hba_rules"] = second["passed"]
        target.rollback(second_state)
        checks["rollback_to_previous_tls_keeps_tls"] = target.metadata()["settings"]["ssl"] == "on"
        target.rollback(upgraded_state)
        # Restore the exact original applied HBA before its matching rollback.
        restored_hba = directory / "postgres/fixture-restored-applied-hba.conf"
        restored_hba.write_bytes(pg.baseline_hba_block(result["baseline_client_address"]).encode()+original_hba.read_bytes())
        target.install_file(restored_hba,before["hba_file"],"600")
        target.query("SELECT pg_reload_conf();")
        target.rollback(state_path)
        after = target.metadata()
        checks["explicit_rollback_restores_settings"] = after["settings"] == before["settings"]
        checks["same_postmaster_after_rollback"] = after["started_at"] == before["started_at"]
        report["passed"] = all(checks.values())
        report["server_version_num"] = before["version"]
        if not report["passed"]:
            pytest.fail("PostgreSQL TLS checks failed: " + ", ".join(name for name, passed in checks.items() if not passed), pytrace=False)
    finally:
        report["checked_at_utc"] = datetime.now(timezone.utc).isoformat()
        path = REPO / "evidence/infra/postgres-tls-integration.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        compose("down", "--volumes", "--remove-orphans")
