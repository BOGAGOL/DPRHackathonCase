"""Invented metadata/URLs only; never open a benchmark or production database."""
from dataclasses import replace
from unittest.mock import MagicMock
import sys

import pytest
from sqlalchemy.engine import make_url

from service_app.config import Settings
from service_app.benchmark_target import benchmark_setup_url, prepare_benchmark_target, verify_benchmark_target
from test_configuration_policy import runtime_url
from test_launcher_guards import load_script


@pytest.fixture
def selection(tmp_path):
    ca = tmp_path / "ca.crt"
    ca.touch()
    target = "api_plain_100k_20261029"
    settings = Settings(mode="plain", database_url=runtime_url(ca, database=target), benchmark_database=target)
    return settings, ca


@pytest.mark.parametrize("mode", ["plain", "protected"])
def test_exact_clone_opt_in_preserves_role_and_tls_guards(selection, mode):
    settings, ca = selection
    settings = replace(settings, mode=mode)
    assert settings.validate() is settings
    with pytest.raises(ValueError): replace(settings, benchmark_database=None).validate()
    for user in ("postgres", "bench_user", "backup_user"):
        with pytest.raises(ValueError): replace(settings, database_url=runtime_url(ca, user=user, database=settings.benchmark_database)).validate()
    for transport in ("disable", "require", "verify-ca"):
        with pytest.raises(ValueError): replace(settings, database_url=runtime_url(ca, database=settings.benchmark_database, sslmode=transport)).validate()


@pytest.mark.parametrize("target", ["postgres", "baseline_100k", "protected_734", "api_", "api_Caps", "api_bad-name", "api_x;DROP DATABASE x", "api_" + "a"*60])
def test_reserved_names_only_and_no_source_override(selection, target):
    settings, ca = selection
    with pytest.raises(ValueError): replace(settings, database_url=runtime_url(ca, database=target), benchmark_database=target).validate()


def test_recovery_and_disposable_flags_cannot_expand_benchmark_selection(selection):
    settings, ca = selection
    with pytest.raises(ValueError): replace(settings, restored_database="dpr_restore_" + "a"*32).validate()
    with pytest.raises(ValueError): replace(settings, allow_disposable_database=True, database_url=runtime_url(ca, database="dpr_b_test_other")).validate()
    assert replace(settings, benchmark_database="api_" + "a"*59, database_url=runtime_url(ca, database="api_" + "a"*59)).validate()


@pytest.mark.parametrize("field,role", [("auth_database_url", "app_user"), ("analyst_database_url", "analyst_user"), ("auditor_database_url", "auditor_user")])
@pytest.mark.parametrize("change", ["database", "host", "port"])
def test_every_connection_stays_on_the_exact_clone(selection, field, role, change):
    settings, ca = selection
    value = make_url(runtime_url(ca, user=role, database=settings.benchmark_database))
    good = value.render_as_string(hide_password=False)
    assert replace(settings, **{field: good}).validate()
    value = value.set(**{change: {"database": "api_other", "host": "other.example.test", "port": 5434}[change]})
    with pytest.raises(ValueError): replace(settings, **{field: value.render_as_string(hide_password=False)}).validate()


def test_target_loaded_from_environment(selection, monkeypatch):
    settings, _ = selection
    monkeypatch.setenv("MODE", settings.mode)
    monkeypatch.setenv("DATABASE_URL", settings.database_url)
    monkeypatch.setenv("DPR_BENCHMARK_DATABASE", settings.benchmark_database)
    assert Settings.from_env().benchmark_database == settings.benchmark_database


@pytest.mark.parametrize("issue", [None, "role", "host", "port", "database", "tls", "ca"])
def test_setup_url_requires_matching_admin_target(selection, issue):
    settings, _ = selection
    value = make_url(settings.database_url).set(username="postgres")
    if issue in {"role", "host", "port", "database"}:
        value = value.set(**{{"role": "username"}.get(issue, issue): {"role": "app_user", "host": "other.example.test", "port": 5434, "database": "protected_734"}[issue]})
    if issue == "tls": value = value.set(query={**value.query, "sslmode": "require"})
    if issue == "ca": value = value.set(query={"sslmode": "verify-full"})
    if issue:
        with pytest.raises(ValueError): benchmark_setup_url(settings, value.render_as_string(hide_password=False))
    else:
        assert benchmark_setup_url(settings, value.render_as_string(hide_password=False)) == value


@pytest.mark.parametrize("mode", ["plain", "protected"])
def test_prepare_grants_only_clone_connect_and_schema_usage(selection, mode):
    settings, _ = selection
    settings = replace(settings, mode=mode)
    connection = MagicMock()
    connection.execute.return_value.one.return_value = (settings.benchmark_database, True)
    connection.scalar.return_value = "invented_table_oid"
    engine = MagicMock()
    engine.begin.return_value.__enter__.return_value = connection
    prepare_benchmark_target(engine, settings)
    queries = [str(call.args[0]) for call in connection.execute.call_args_list]
    assert any('GRANT CONNECT ON DATABASE "' + settings.benchmark_database + '"' in query for query in queries)
    assert any("GRANT USAGE ON SCHEMA public" in query for query in queries)
    assert any("dpr-service-benchmark-v1:" + mode in query for query in queries)
    assert not any(word in query for query in queries for word in ("CREATE DATABASE", "DROP", "RENAME", "INSERT", "UPDATE", "BYPASSRLS"))


@pytest.mark.parametrize("issue", ["database", "tls", "schema"])
def test_prepare_refuses_wrong_target_before_any_grants(selection, issue):
    settings, _ = selection
    connection = MagicMock()
    connection.execute.return_value.one.return_value = ("protected_734" if issue == "database" else settings.benchmark_database, issue != "tls")
    connection.scalar.return_value = None if issue == "schema" else "invented_table_oid"
    engine = MagicMock()
    engine.begin.return_value.__enter__.return_value = connection
    with pytest.raises(ValueError): prepare_benchmark_target(engine, settings)
    assert not any("GRANT" in str(call.args[0]) or "COMMENT" in str(call.args[0]) for call in connection.execute.call_args_list)


def metadata(target, mode):
    connection = MagicMock()
    connection.execute.return_value.one.side_effect = [(target, "app_user", True, "dpr-service-benchmark-v1:" + mode, False, False), ("schema_owner", True, True)]
    connection.scalar.return_value = "invented_table_oid"
    return connection


@pytest.mark.parametrize("mode", ["plain", "protected"])
def test_startup_gate_is_read_only_metadata(selection, mode):
    settings, _ = selection
    connection = metadata(settings.benchmark_database, mode)
    verify_benchmark_target(connection, settings.benchmark_database, mode)
    assert str(connection.execute.call_args_list[0].args[0]) == "SET TRANSACTION READ ONLY"
    assert connection.scalar.call_count == (4 if mode == "plain" else 7)
    assert not any("_ct" in str(call.args[0]) or "SELECT *" in str(call.args[0]) for call in connection.execute.call_args_list)


@pytest.mark.parametrize("index,value", [(0, "protected_734"), (1, "postgres"), (2, False), (3, "missing_marker"), (4, True), (5, True)])
def test_startup_gate_rejects_unsafe_state(selection, index, value):
    settings, _ = selection
    state = [settings.benchmark_database, "app_user", True, "dpr-service-benchmark-v1:plain", False, False]
    state[index] = value
    connection = MagicMock()
    connection.execute.return_value.one.return_value = tuple(state)
    with pytest.raises(ValueError): verify_benchmark_target(connection, settings.benchmark_database, "plain")


def test_startup_refuses_incomplete_schema_or_unforced_rls(selection):
    settings, _ = selection
    connection = metadata(settings.benchmark_database, "plain")
    connection.scalar.return_value = None
    with pytest.raises(ValueError): verify_benchmark_target(connection, settings.benchmark_database, "plain")
    connection = metadata(settings.benchmark_database, "protected")
    connection.execute.return_value.one.side_effect = [(settings.benchmark_database, "app_user", True, "dpr-service-benchmark-v1:protected", False, False), ("schema_owner", True, False)]
    with pytest.raises(ValueError): verify_benchmark_target(connection, settings.benchmark_database, "protected")


@pytest.mark.parametrize("mode", ["plain", "protected"])
def test_schema_cli_routes_api_named_clone_by_mode(selection, monkeypatch, mode):
    settings, _ = selection
    settings = replace(settings, mode=mode)
    module = load_script("schema")
    monkeypatch.setenv("DPR_BENCHMARK_DATABASE", settings.benchmark_database)
    monkeypatch.setenv("APP_SETUP_DATABASE_URL", make_url(settings.database_url).set(username="postgres").render_as_string(hide_password=False))
    monkeypatch.setattr(module.Settings, "from_env", lambda: settings)
    monkeypatch.setattr(sys, "argv", ["schema.py", "--database", settings.benchmark_database])
    engine = MagicMock()
    engine.begin.return_value.__enter__.return_value.execute.return_value.scalar.return_value = None
    monkeypatch.setattr(module, "create_engine", lambda *a, **kw: engine)
    prepare, protected = MagicMock(), MagicMock()
    monkeypatch.setattr(module, "prepare_benchmark_target", prepare)
    monkeypatch.setattr(module, "setup_protected", protected)
    for model in (module.User, module.Session, module.AuditLog): monkeypatch.setattr(model.__table__, "create", MagicMock())
    module.main()
    prepare.assert_called_once_with(engine, settings)
    assert protected.call_count == int(mode == "protected")
    if mode == "plain":
        queries = [str(call.args[0]) for call in engine.begin.return_value.__enter__.return_value.execute.call_args_list]
        assert "GRANT SELECT, INSERT, UPDATE ON anggota TO app_user" in queries
    engine.dispose.assert_called_once()


@pytest.mark.parametrize("mode", ["plain", "protected"])
def test_provisioning_uses_clone_setup_guard_in_both_modes(selection, monkeypatch, tmp_path, mode):
    settings, _ = selection
    settings = replace(settings, mode=mode)
    module = load_script("provision")
    monkeypatch.setattr(module.Settings, "from_env", lambda: settings)
    monkeypatch.setenv("DPR_PRIVATE_DIR", str(tmp_path))
    monkeypatch.setenv("APP_SETUP_DATABASE_URL", make_url(settings.database_url).set(username="postgres").render_as_string(hide_password=False))
    monkeypatch.setattr(module, "secure_directory", lambda path: path)
    guard = MagicMock(side_effect=ValueError("invented setup refusal"))
    monkeypatch.setattr(module, "benchmark_setup_url", guard)
    connect = MagicMock()
    monkeypatch.setattr(module, "create_engine", connect)
    with pytest.raises(ValueError, match="invented setup refusal"): module.main()
    guard.assert_called_once()
    connect.assert_not_called()


def test_failed_startup_gate_closes_dependencies(selection, monkeypatch):
    import service_app.main as main
    settings, _ = selection
    engine = MagicMock()
    monkeypatch.setattr(main, "create_engine", lambda *a, **kw: engine)
    monkeypatch.setattr(main, "verify_benchmark_target", MagicMock(side_effect=ValueError("invented rejection")))
    with pytest.raises(ValueError, match="Verified benchmark clone unavailable"): main.create_app(settings)
    engine.dispose.assert_called_once()
