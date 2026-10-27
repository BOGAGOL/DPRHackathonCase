"""Privileged setup/credential launchers must reject unsafe inputs before DB/network use."""
import importlib.util
from pathlib import Path
import secrets
import sys

import pytest
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.engine import URL
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session as DBSession

from service_app.config import Settings
from service_app.models import User, source_type


APP = Path(__file__).resolve().parents[1]


def load_script(name):
    path = APP / "scripts" / (name + ".py")
    spec = importlib.util.spec_from_file_location("module_b_guard_test_" + name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("case", ["missing", "nonexistent_cert", "nonexistent_key"])
def test_api_launcher_refuses_missing_https_material(monkeypatch, tmp_path, case):
    module = load_script("serve")
    monkeypatch.delenv("TLS_CERT_FILE", raising=False)
    monkeypatch.delenv("TLS_KEY_FILE", raising=False)
    if case != "missing":
        cert, key = tmp_path / "cert.crt", tmp_path / "key.key"
        (key if case == "nonexistent_cert" else cert).touch()
        monkeypatch.setenv("TLS_CERT_FILE", str(cert))
        monkeypatch.setenv("TLS_KEY_FILE", str(key))
    def forbidden(*args, **kwargs):
        raise AssertionError("Network launcher must not run")
    monkeypatch.setattr(module.uvicorn, "run", forbidden)
    with pytest.raises(ValueError):
        module.main()


def test_api_launcher_passes_https_files_and_disables_request_logging(monkeypatch, tmp_path):
    module = load_script("serve")
    cert, key = tmp_path / "cert.crt", tmp_path / "key.key"
    cert.touch()
    key.touch()
    monkeypatch.setenv("TLS_CERT_FILE", str(cert))
    monkeypatch.setenv("TLS_KEY_FILE", str(key))
    monkeypatch.setenv("API_PORT", "8100")
    captured = {}
    def launch(application, **kwargs):
        captured.update(application=application, **kwargs)
    monkeypatch.setattr(module.uvicorn, "run", launch)
    module.main()
    assert captured["ssl_certfile"] == str(cert) and captured["ssl_keyfile"] == str(key)
    assert captured["access_log"] is False and captured["proxy_headers"] is False
    assert captured["host"] == "127.0.0.1" and captured["port"] == 8100


def test_schema_setup_rejects_original_database_before_connect(monkeypatch):
    module = load_script("schema")
    monkeypatch.setattr(sys, "argv", ["schema.py", "--database", "postgres"])
    def forbidden(*args, **kwargs):
        raise AssertionError("Database connection must not be attempted")
    monkeypatch.setattr(module, "create_engine", forbidden)
    with pytest.raises(SystemExit) as caught:
        module.main()
    assert caught.value.code == 2


@pytest.mark.parametrize("database,sslmode,include_ca", [
    ("protected_100k", "verify-full", True),
    ("postgres", "verify-full", True),
    ("baseline_100k", "require", True),
    ("baseline_100k", "disable", True),
    ("baseline_100k", "verify-full", False),
])
def test_schema_setup_rejects_url_mismatch_or_unverified_transport(monkeypatch, tmp_path, database, sslmode, include_ca):
    module = load_script("schema")
    query = {"sslmode": sslmode}
    if include_ca:
        query["sslrootcert"] = str(tmp_path / "trusted.crt")
    url = URL.create("postgresql+psycopg", username="migration_user", password=secrets.token_urlsafe(24),
                     host="localhost", database=database, query=query).render_as_string(hide_password=False)
    monkeypatch.setenv("APP_SETUP_DATABASE_URL", url)
    monkeypatch.setattr(sys, "argv", ["schema.py", "--database", "baseline_100k"])
    def forbidden(*args, **kwargs):
        raise AssertionError("Database connection must not be attempted")
    monkeypatch.setattr(module, "create_engine", forbidden)
    with pytest.raises(ValueError):
        module.main()


@pytest.mark.parametrize("relative", [".", "app", "app/.local/private-output"])
def test_provisioning_refuses_repo_private_paths_before_database(monkeypatch, relative):
    module = load_script("provision")
    settings = Settings(mode="plain", database_url="sqlite://", testing=True)
    monkeypatch.setattr(module.Settings, "from_env", classmethod(lambda cls: settings))
    monkeypatch.setenv("DPR_PRIVATE_DIR", str(module.ROOT / relative))
    def forbidden(*args, **kwargs):
        raise AssertionError("Database connection must not be attempted")
    monkeypatch.setattr(module, "create_engine", forbidden)
    with pytest.raises(ValueError):
        module.main()


@pytest.mark.parametrize("target", ["ancestor", "home", "drive_root"])
def test_provisioning_rejects_ancestor_home_or_root_before_acl(monkeypatch, target):
    module = load_script("provision")
    settings = Settings(mode="plain", database_url="sqlite://", testing=True)
    monkeypatch.setattr(module.Settings, "from_env", classmethod(lambda cls: settings))
    destination = {"ancestor": module.ROOT.parent, "home": Path.home(), "drive_root": Path(module.ROOT.anchor)}[target]
    monkeypatch.setenv("DPR_PRIVATE_DIR", str(destination))
    def forbidden(*args, **kwargs):
        raise AssertionError("No ACL or database action may occur")
    monkeypatch.setattr(module, "secure_directory", forbidden)
    monkeypatch.setattr(module, "create_engine", forbidden)
    with pytest.raises(ValueError):
        module.main()


def test_provisioning_applies_private_directory_guard_before_database_or_output(monkeypatch, tmp_path, capsys):
    module = load_script("provision")
    settings = Settings(mode="plain", database_url="sqlite://", testing=True)
    monkeypatch.setattr(module.Settings, "from_env", classmethod(lambda cls: settings))
    monkeypatch.setenv("DPR_PRIVATE_DIR", str(tmp_path))
    # No real host ACL is changed. The sequence is observed with a test-only directory facade.
    monkeypatch.setattr(module, "external_directory", lambda value: tmp_path)
    events = []
    def secure(path):
        assert path == tmp_path / "service-b"
        assert not (path / "service-b-plain-accounts.json").exists()
        events.append("private-directory")
        return path
    class StopBeforeDatabase(Exception):
        pass
    def database(*args, **kwargs):
        events.append("database")
        raise StopBeforeDatabase()
    monkeypatch.setattr(module, "secure_directory", secure)
    monkeypatch.setattr(module, "create_engine", database)
    with pytest.raises(StopBeforeDatabase):
        module.main()
    assert events == ["private-directory", "database"]
    assert not (tmp_path / "service-b/service-b-plain-accounts.json").exists()
    assert str(tmp_path) not in capsys.readouterr().out


def test_protected_provision_stores_only_index_binding_not_source_identifier(monkeypatch, tmp_path, capsys):
    module = load_script("provision")
    database_url = "sqlite:///" + str(tmp_path / "control.sqlite")
    settings = Settings(mode="protected", database_url=database_url, testing=True)
    engine = create_engine(database_url)
    User.__table__.create(engine)
    monkeypatch.setattr(module.Settings, "from_env", classmethod(lambda cls: settings))
    monkeypatch.setenv("DPR_PRIVATE_DIR", str(tmp_path))
    original_identifier = "synthetic-" + secrets.token_urlsafe(12)
    expected_index = secrets.token_bytes(32)
    monkeypatch.setenv("DEMO_MEMBER_PRINCIPAL", original_identifier)
    monkeypatch.setattr(module, "external_directory", lambda value: tmp_path)
    def private(path):
        path.mkdir()
        return path
    monkeypatch.setattr(module, "secure_directory", private)
    class TestAdapter:
        def __init__(self, config):
            pass
        def blind_index(self, field, value):
            assert field == "pengguna" and value == original_identifier
            return expected_index
    monkeypatch.setattr(module, "ToolkitAdapter", TestAdapter)
    module.main()
    with DBSession(engine) as db:
        users = db.scalars(select(User)).all()
        assert len(users) == 6
        assert all(u.principal != original_identifier for u in users)
        member = next(u for u in users if u.role == "anggota")
        assert member.principal == "bidx:v1:" + expected_index.hex()
        assert all(u.principal == u.id for u in users if u.role != "anggota")
    output = tmp_path / "service-b/service-b-protected-accounts.json"
    serialized = output.read_text(encoding="utf-8")
    stdout = capsys.readouterr().out
    assert original_identifier not in serialized and original_identifier not in stdout
    assert str(tmp_path) not in stdout
    import json
    assert not any(a["password"] in stdout for a in json.loads(serialized))
    engine.dispose()


@pytest.mark.parametrize("field,pg_type", [("tanggal_lahir", "DATE"), ("tanggal_pernikahan", "DATE"),
                                           ("jumlah_anak", "SMALLINT"), ("jumlah_tanggungan", "SMALLINT"), ("nama", "TEXT")])
def test_source_types_match_native_postgres_and_isolated_sqlite(field, pg_type):
    assert source_type(field).compile(dialect=postgresql.dialect()) == pg_type
    assert source_type(field).compile(dialect=sqlite.dialect()) == "TEXT"
