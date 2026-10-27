from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
from unittest.mock import Mock

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
import pytest

from infra.postgres import enable_tls as pg
from infra.postgres import make_cert
from infra.security import secure_directory
from infra.tls.make_ca import make_ca
from migration.connection import connection_parameters


@pytest.fixture
def tls_root(tmp_path):
    make_ca(tmp_path / "tls")
    return tmp_path


def sample_metadata():
    return {"version": 180006, "superuser": True, "data_directory": "/var/lib/postgresql/18/docker",
            "hba_file": "/var/lib/postgresql/18/docker/pg_hba.conf", "started_at": "synthetic-start-time",
            "command_line_override": False, "contexts": {name: "sighup" for name in pg.SSL_SETTINGS},
            "settings": {"ssl": "off", "ssl_cert_file": "server.crt", "ssl_key_file": "server.key", "ssl_min_protocol_version": "TLSv1.2"},
            "overrides": {}, "database_oids": {"postgres": 5, "baseline_100k": 16384}}


def test_postgres_ca_signed_leaf_san_expiry_and_exclusive_generation(tls_root):
    directory = make_cert.make_certificate(tls_root, dns_names=("db.example.test",), ip_addresses=("192.0.2.10",))
    ca = x509.load_pem_x509_certificate((directory / "ca.crt").read_bytes())
    leaf = x509.load_pem_x509_certificate((directory / "server.crt").read_bytes())
    key = serialization.load_pem_private_key((directory / "server.key").read_bytes(), password=None)
    ca.public_key().verify(leaf.signature, leaf.tbs_certificate_bytes, padding.PKCS1v15(), leaf.signature_hash_algorithm)
    assert leaf.public_key().public_numbers() == key.public_key().public_numbers()
    sans = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert set(sans.get_values_for_type(x509.DNSName)) == {"pg-dpr", "localhost", "host.docker.internal", "db.example.test"}
    assert datetime.now(timezone.utc) < leaf.not_valid_after_utc <= ca.not_valid_after_utc
    assert not (directory / "ca.key").exists()
    with pytest.raises(ValueError):
        make_cert.make_certificate(tls_root)


def test_certificate_cli_and_invalid_san(tls_root, monkeypatch, capsys):
    with pytest.raises(ValueError):
        make_cert.make_certificate(tls_root, dns_names=("bad host",))
    monkeypatch.setenv("DPR_SECRETS_DIR", str(tls_root))
    monkeypatch.setattr("sys.argv", ["make-cert"])
    make_cert.main()
    assert "outside the repository" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        make_cert.main()


def test_hba_block_is_idempotent_and_preserves_existing_auth_rules():
    original = b"# existing rules\nlocal all all trust\nhost all all all scram-sha-256\n"
    modified = pg.managed_hba(original)
    assert modified == pg.HBA_BLOCK.encode() + original
    assert pg.managed_hba(modified) == modified
    assert "postgres," not in pg.HBA_BLOCK
    with pytest.raises(pg.TLSUpdateError):
        pg.managed_hba(b"# BEGIN DPR PROJECT TLS\nunexpected configuration\n")


def test_state_save_is_atomic(tmp_path):
    directory = secure_directory(tmp_path / "private")
    path = directory / "state.json"
    pg.save_state(path, {"status": "prepared"})
    pg.save_state(path, {"status": "applied"})
    assert json.loads(path.read_text()) == {"status": "applied"}
    assert not list(directory.glob("*.tmp"))


def test_metadata_requires_reloadable_pg18_on_persistent_mount():
    target = pg.ExistingPostgres.__new__(pg.ExistingPostgres)
    target.container, target.admin = "synthetic-container", "synthetic-admin"
    target.run = Mock(return_value="")
    target.info = {"Mounts": [{"Destination": "/var/lib/postgresql", "Type": "volume", "RW": True}]}
    metadata = sample_metadata()
    target.query = Mock(return_value=json.dumps(metadata))
    assert target.metadata() == metadata
    for change in ({"version": 170000}, {"superuser": False}, {"command_line_override": True},
                   {"hba_file": "/etc/pg_hba.conf"}, {"contexts": {"ssl": "postmaster"}}):
        target.query.return_value = json.dumps({**metadata, **change})
        with pytest.raises(pg.TLSUpdateError):
            target.metadata()


def test_container_validation_and_sanitized_execution(monkeypatch):
    info = {"Id": "synthetic-id", "State": {"Running": True}, "Config": {"Env": ["POSTGRES_USER=admin_role"]},
            "NetworkSettings": {"Ports": {"5432/tcp": [{"HostPort": "5433"}]}}}
    monkeypatch.setattr(subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps([info]), "")))
    target = pg.ExistingPostgres()
    assert target.admin == "admin_role" and target.port == 5433
    with pytest.raises(pg.TLSUpdateError):
        pg.ExistingPostgres("bad/name")
    info["State"]["Running"] = False
    subprocess.run.return_value.stdout = json.dumps([info])
    with pytest.raises(pg.TLSUpdateError):
        pg.ExistingPostgres()
    subprocess.run.return_value = subprocess.CompletedProcess([], 1, "", "sensitive-error-body")
    with pytest.raises(pg.TLSUpdateError) as caught:
        target.run(["inspect", "pg-dpr"])
    assert "sensitive-error-body" not in str(caught.value)


def test_alter_system_quotes_values_and_preserves_other_settings():
    target = pg.ExistingPostgres.__new__(pg.ExistingPostgres)
    target.query = Mock()
    target.alter("ssl", "on")
    assert target.query.call_args.args[0] == 'ALTER SYSTEM SET "ssl" TO \'on\';'
    target.alter("ssl_cert_file", "/path/with'quote.crt")
    assert "with''quote.crt" in target.query.call_args.args[0]
    target.alter("ssl", None)
    assert target.query.call_args.args[0] == 'ALTER SYSTEM RESET "ssl";'
    with pytest.raises(pg.TLSUpdateError):
        target.alter("primary_conninfo", "")


def test_migration_targets_tls_and_source_read_only(tmp_path, monkeypatch):
    ca = tmp_path / "ca.crt"
    ca.write_text("synthetic test path; no connection attempted")
    monkeypatch.setenv("PGSSLROOTCERT", str(ca))
    monkeypatch.setenv("PGUSER", "migration_user")
    monkeypatch.setenv("PGPASSWORD", os.urandom(24).hex())
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.delenv("PGPORT", raising=False)
    for database in ("protected_734", "protected_100k"):
        params = connection_parameters(database)
        assert params["host"] == "127.0.0.1" and params["port"] == 5433
        assert params["sslmode"] == "verify-full" and params["dbname"] == database
    for database in ("postgres", "baseline_100k"):
        with pytest.raises(ValueError):
            connection_parameters(database)
        assert "read_only=on" in connection_parameters(database, source=True)["options"]
    monkeypatch.setenv("PGPORT", "5434")
    with pytest.raises(ValueError):
        connection_parameters("protected_734")


def test_inspect_cli_records_failure_without_claiming_live_success(tmp_path, monkeypatch):
    monkeypatch.setattr(pg, "REPO", tmp_path)
    monkeypatch.setattr("sys.argv", ["enable-tls", "inspect"])
    monkeypatch.setattr(pg, "ExistingPostgres", Mock(side_effect=pg.TLSUpdateError("target_missing")))
    with pytest.raises(SystemExit):
        pg.main()
    report = json.loads((tmp_path / "evidence/infra/postgres-tls.json").read_text())
    assert not report["passed"] and report["error"] == "target_missing"
    target = Mock()
    target.metadata.return_value = sample_metadata()
    pg.ExistingPostgres.return_value = target
    pg.ExistingPostgres.side_effect = None
    pg.main()
    assert json.loads((tmp_path / "evidence/infra/postgres-tls.json").read_text())["passed"]
