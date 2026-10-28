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


def test_hba_upgrade_adds_1m_and_preserves_existing_tail():
    tail=b"local all all trust\nhost all all all scram-sha-256\n"
    upgraded=pg.managed_hba(pg.LEGACY_HBA_BLOCK.encode()+tail)
    assert upgraded==pg.HBA_BLOCK.encode()+tail
    assert "baseline_1m,protected_1m" in pg.HBA_BLOCK
    assert pg.managed_hba(upgraded)==upgraded
    with pytest.raises(pg.TLSUpdateError):pg.managed_hba(upgraded+pg.LEGACY_HBA_BLOCK.encode())


def test_hba_upgrade_covers_restore_names_and_preserves_previous_baseline_exception():
    tail = b"hostssl all all 0.0.0.0/0 cert\n"
    old = pg.baseline_hba_block("172.17.0.1").replace(pg.RESTORE_HBA_RULES, "").encode()+tail
    assert pg.managed_hba(old, "172.17.0.1") == pg.baseline_hba_block("172.17.0.1").encode()+tail
    assert pg.managed_hba(pg.PRE_RESTORE_HBA_BLOCK.encode()+tail) == pg.HBA_BLOCK.encode()+tail
    assert pg.RESTORE_HBA_RULES.count('"/^dpr_restore_[0-9a-f]{32}$"') == 2
    assert "baseline_" not in pg.RESTORE_HBA_RULES


@pytest.mark.parametrize("address,cidr", [("172.17.0.1", "172.17.0.1/32"), ("::1", "::1/128")])
def test_baseline_exception_is_exact_and_precedes_reject(address, cidr):
    tail = b"local all all trust\nhost all all all scram-sha-256\n"
    expected = pg.baseline_hba_block(address).encode() + tail
    for prior in (tail, pg.LEGACY_HBA_BLOCK.encode() + tail, pg.HBA_BLOCK.encode() + tail, expected):
        assert pg.managed_hba(prior, address) == expected
    block = pg.baseline_hba_block(address)
    assert block.splitlines()[1] == "hostnossl baseline_100k,baseline_1m bench_user,scanner_user " + cidr + " scram-sha-256"
    assert block.index("scram-sha-256") < block.index(" all 0.0.0.0/0 reject")
    for invalid in ("0.0.0.0/0", "172.17.0.0/16", "0.0.0.0", "::", "224.0.0.1", "fe80::1%eth0", "bad\nhost all all all trust"):
        with pytest.raises(ValueError):
            pg.baseline_hba_block(invalid)
    with pytest.raises(pg.TLSUpdateError):
        pg.managed_hba(expected + pg.HBA_BLOCK.encode(), address)


def test_baseline_credentials_are_required_without_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("DPR_BENCH_USER_PASSWORD", raising=False)
    with pytest.raises(pg.TLSUpdateError, match="baseline_bench_credential_required"):
        pg.baseline_passwords(tmp_path)
    password = os.urandom(24).hex()
    monkeypatch.setenv("DPR_BENCH_USER_PASSWORD", password)
    monkeypatch.setattr(pg, "role_password", Mock(return_value=password))
    assert set(pg.baseline_passwords(tmp_path)) == set(pg.BASELINE_ROLES)
    existing = os.urandom(5).hex()
    monkeypatch.setenv("DPR_SCANNER_USER_PASSWORD", existing)
    assert pg.baseline_passwords(tmp_path)["scanner_user"] == existing


def test_connection_matrix_checks_real_baseline_roles_and_protected_tls(tmp_path, monkeypatch):
    password = os.urandom(24).hex()
    monkeypatch.setenv("DPR_BENCH_USER_PASSWORD", password)
    monkeypatch.setenv("DPR_APP_USER_PASSWORD", password)
    monkeypatch.setattr(pg, "role_password", Mock(return_value=password))
    rejected = Mock(return_value=True)
    monkeypatch.setattr(pg, "plaintext_rejected", rejected)
    calls = []

    def connect(**params):
        calls.append(params)
        connection = Mock()
        connection.execute.return_value.fetchone.return_value = (params["user"], params["dbname"], params["sslmode"] == "verify-full")
        context = Mock()
        context.__enter__ = Mock(return_value=connection)
        context.__exit__ = Mock(return_value=False)
        return context

    monkeypatch.setattr(pg.psycopg, "connect", connect)
    existing = {"baseline_100k": 1, "baseline_1m": 2, "protected_100k": 123}
    checks = pg.connection_matrix(tmp_path, "127.0.0.1", 5433, existing, "172.17.0.1")
    assert all(checks.values())
    assert len([call for call in calls if call["sslmode"] == "disable"]) == 4
    assert {call["user"] for call in calls if call["sslmode"] == "disable"} == set(pg.BASELINE_ROLES)
    assert calls[-1]["user"] == "app_user" and calls[-1]["sslmode"] == "verify-full"
    assert calls[-1]["sslrootcert"] == str(tmp_path / "postgres/tls/ca.crt")
    assert "protected_verify_full:protected_734" not in checks  # not yet prepared
    assert rejected.call_count == len(pg.BASELINES)*9+(len(pg.DATABASES)-len(pg.BASELINES))*11+6
    assert all(checks["restore_plaintext_rejected:"+role] for role in ("app_user", "backup_user", "analyst_user", "auditor_user", *pg.BASELINE_ROLES))
    assert ("127.0.0.1",5433,"protected_100k","bench_user") in [call.args for call in rejected.call_args_list]
    assert not pg.matrix_coverage(existing,checks,"172.17.0.1")["connection_matrix_complete"]
    monkeypatch.setattr(pg.psycopg, "connect", Mock(side_effect=pg.psycopg.OperationalError("withheld")))
    failed = pg.connection_matrix(tmp_path, "127.0.0.1", 5433, existing, "172.17.0.1")
    assert not failed["baseline_plaintext_allowed:baseline_100k:bench_user"]
    assert not failed["protected_verify_full:protected_100k"]
    partial = pg.connection_matrix(tmp_path,"127.0.0.1",5433,{"baseline_100k":1},"172.17.0.1")
    assert "baseline_plaintext_allowed:baseline_1m:bench_user" not in partial
    assert pg.matrix_coverage({"baseline_100k":1},partial,"172.17.0.1")["baseline_databases_pending"]==["baseline_1m"]


def test_hba_address_change_removal_and_legacy_exception_upgrade():
    tail = b"hostssl all all 0.0.0.0/0 cert\nlocal all all peer\n"
    old = pg.baseline_hba_block("172.17.0.1").encode()+tail
    legacy = old.replace(b"hostnossl baseline_",b"host baseline_",1)
    new = pg.baseline_hba_block("192.168.65.1").encode()+tail
    assert pg.split_managed_hba(old) == (tail,"172.17.0.1")
    assert pg.managed_hba(old,"192.168.65.1") == new
    assert pg.managed_hba(legacy,"192.168.65.1") == new
    assert pg.managed_hba(new) == pg.HBA_BLOCK.encode()+tail
    for broken in (old.replace(b"/32",b"/0"),old.replace(b"bench_user,scanner_user",b"all"),
                   old.replace(b"scram-sha-256",b"trust"),old+pg.HBA_BLOCK.encode()):
        with pytest.raises(pg.TLSUpdateError): pg.split_managed_hba(broken)


def test_strict_matrix_does_not_require_benchmark_roles_or_credentials(tmp_path,monkeypatch):
    monkeypatch.setattr(pg,"baseline_passwords",Mock(side_effect=AssertionError("must not load")))
    monkeypatch.setattr(pg,"optional_role_password",Mock(return_value=None))
    rejected=Mock(return_value=True);monkeypatch.setattr(pg,"plaintext_rejected",rejected)
    checks=pg.connection_matrix(tmp_path,"127.0.0.1",5433,{})
    assert all(checks.values()) and rejected.call_count==len(pg.DATABASES)*11+6
    assert not any(name.startswith("baseline_plaintext_allowed:") for name in checks)
    assert pg.matrix_coverage({},checks,None)["protected_databases_pending_prepare"]==["protected_734","protected_100k","protected_1m"]


def test_optional_role_password_and_hba_catalog_read(tmp_path,monkeypatch):
    import base64
    monkeypatch.delenv("DPR_APP_USER_PASSWORD",raising=False)
    assert pg.optional_role_password(tmp_path,"app_user") is None
    folder=tmp_path/"postgres/roles";folder.mkdir(parents=True)
    (folder/"app_user.credential.xml").touch()
    password=os.urandom(24).hex();monkeypatch.setattr(pg,"role_password",Mock(return_value=password))
    assert pg.optional_role_password(tmp_path,"app_user")==password
    target=pg.ExistingPostgres.__new__(pg.ExistingPostgres)
    expected=pg.HBA_BLOCK.encode()+b"local all all peer\n"
    target.query=Mock(return_value=base64.b64encode(expected).decode())
    assert target.read_hba()==expected


def test_plaintext_probe_requires_hba_rejection_not_wrong_password(monkeypatch):
    connect = Mock(side_effect=pg.psycopg.OperationalError("pg_hba.conf rejects connection: no encryption"))
    monkeypatch.setattr(pg.psycopg, "connect", connect)
    assert pg.plaintext_rejected("127.0.0.1", 5433, "protected_100k", "app_user")
    assert connect.call_args.kwargs["user"] == "app_user"
    connect.side_effect = pg.psycopg.OperationalError("password authentication failed")
    assert not pg.plaintext_rejected("127.0.0.1", 5433, "protected_100k", "app_user")


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


def test_cli_configures_address_and_verify_never_changes_hba(tmp_path,monkeypatch):
    monkeypatch.setattr(pg,"REPO",tmp_path)
    monkeypatch.setenv("DPR_SECRETS_DIR",str(tmp_path/"private"))
    monkeypatch.setenv("DPR_BASELINE_CLIENT_ADDRESS","auto")
    target=Mock();target.apply.return_value=(tmp_path/"private/change/state.json",{"passed":True})
    target.metadata.return_value=sample_metadata()
    target.read_hba.return_value=pg.baseline_hba_block("172.17.0.1").encode()+b"local all all peer\n"
    monkeypatch.setattr(pg,"ExistingPostgres",Mock(return_value=target))
    monkeypatch.setattr("sys.argv",["enable-tls","apply"])
    pg.main()
    assert target.apply.call_args.kwargs=={"baseline_address":"auto"}
    monkeypatch.setattr(pg,"verify_tls",Mock(return_value={"hostname_verified":True}))
    monkeypatch.setattr(pg,"connection_matrix",Mock(return_value={"example_check":True}))
    target.metadata.return_value={**sample_metadata(),"settings":{"ssl":"on"}}
    monkeypatch.setattr("sys.argv",["enable-tls","verify"])
    pg.main()
    assert target.apply.call_count==1
    monkeypatch.setattr("sys.argv",["enable-tls","verify","--baseline-client-address","192.168.65.1"])
    with pytest.raises(SystemExit): pg.main()
    report=json.loads((tmp_path/"evidence/infra/postgres-tls.json").read_text())
    assert not report["checks"]["configured_baseline_address_matches"]
