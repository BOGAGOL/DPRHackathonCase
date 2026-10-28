from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from service_app.config import Settings
from service_app.recovery import verify_restore_target
from test_configuration_policy import runtime_url


def test_recovery_requires_explicit_exact_target_and_verified_role_tls(tmp_path):
    ca = tmp_path/"ca.crt"; ca.touch()
    target = "dpr_restore_"+uuid4().hex
    url = runtime_url(ca, database=target)
    with pytest.raises(ValueError): Settings(mode="protected", database_url=url).validate()
    assert Settings(mode="protected", database_url=url, restored_database=target).validate()
    for mode, chosen, runtime in (("plain", target, target), ("protected", "postgres", "postgres"),
            ("protected", target, "protected_734"), ("protected", target, "dpr_restore_"+uuid4().hex)):
        with pytest.raises(ValueError): Settings(mode=mode, database_url=runtime_url(ca, database=runtime), restored_database=chosen).validate()
    for role in ("postgres", "backup_user"):
        with pytest.raises(ValueError): Settings(mode="protected", database_url=runtime_url(ca, user=role, database=target), restored_database=target).validate()
    for tls in ("disable", "require", "verify-ca"):
        with pytest.raises(ValueError): Settings(mode="protected", database_url=runtime_url(ca, database=target, sslmode=tls), restored_database=target).validate()
    with pytest.raises(ValueError):
        Settings(mode="protected", database_url=url, restored_database=target,
                 auditor_database_url=runtime_url(ca, user="auditor_user", database="protected_734")).validate()


def metadata_connection(target, *, marker=None, unsafe=False, tls=True, extra_table=False, rls=True):
    connection = MagicMock()
    state = (target, "app_user", tls, marker or "dpr-service-restore-v1:"+str(uuid4()), unsafe, False)
    tables = ["access_scope", "anggota_protected", "app_users", "audit_log", "migration_jobs", "service_member_bindings", "service_sessions"]
    if extra_table: tables.append("unreviewed")
    connection.execute.side_effect = [MagicMock(), MagicMock(one=lambda: state),
        MagicMock(scalars=lambda: MagicMock(all=lambda: tables)), MagicMock(one=lambda: ("schema_owner", True, rls))]
    return connection


def test_startup_verifies_completed_restore_metadata_without_reading_member_values():
    target = "dpr_restore_"+uuid4().hex
    connection = metadata_connection(target)
    verify_restore_target(connection, target)
    assert connection.execute.call_count == 4


@pytest.mark.parametrize("options", [{"marker":"dpr-backup-v1:"+str(uuid4())}, {"marker":"dpr-service-restore-v1:invalid"},
    {"unsafe":True}, {"tls":False}, {"extra_table":True}, {"rls":False}])
def test_startup_refuses_unverified_or_unsafe_restored_target(options):
    target = "dpr_restore_"+uuid4().hex
    with pytest.raises(ValueError, match="Verified service restore target required"):
        verify_restore_target(metadata_connection(target, **options), target)


def test_restore_target_setting_loaded_from_env(monkeypatch, tmp_path):
    ca = tmp_path/"ca.crt"; ca.touch()
    target = "dpr_restore_"+uuid4().hex
    monkeypatch.setenv("MODE", "protected")
    monkeypatch.setenv("DATABASE_URL", runtime_url(ca, database=target))
    monkeypatch.setenv("DPR_RESTORED_DATABASE", target)
    assert Settings.from_env().restored_database == target


def test_failed_recovery_gate_closes_dependencies_before_serving(monkeypatch, tmp_path):
    import service_app.main as main
    ca = tmp_path/"ca.crt"; ca.touch()
    target = "dpr_restore_"+uuid4().hex
    settings = Settings(mode="protected", database_url=runtime_url(ca, database=target), restored_database=target)
    engine = MagicMock(); driver = MagicMock()
    monkeypatch.setattr(main,"create_engine",lambda *args,**kwargs:engine)
    monkeypatch.setattr(main,"ToolkitAdapter",lambda settings:driver)
    gate = MagicMock(side_effect=ValueError("Synthetic metadata rejection"))
    monkeypatch.setattr(main,"verify_restore_target",gate)
    with pytest.raises(ValueError,match="Verified service restore target unavailable"):
        main.create_app(settings)
    gate.assert_called_once()
    engine.dispose.assert_called_once()
    driver.close.assert_called_once()
