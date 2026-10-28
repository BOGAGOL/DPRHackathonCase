from unittest.mock import MagicMock
import os

import pytest

from scripts.backup import postgres as pg
from scripts.backup.crypto import BackupError


@pytest.mark.parametrize("names", [pg.TABLES, pg.SERVICE_TABLES])
def test_count_reviewed_layout_without_reading_values(names):
    connection = MagicMock()
    connection.execute.side_effect = [[(name,) for name in names], *[MagicMock(fetchone=lambda: (17,)) for _ in names]]
    assert pg.row_counts(connection) == dict.fromkeys(names, 17)


@pytest.mark.parametrize("names", [(), (*pg.TABLES, "service_sessions"), (*pg.TABLES, "service_member_bindings"), (*pg.SERVICE_TABLES, "unknown"), (*pg.TABLES, "app_users"), (None, "app_users")])
def test_partial_extra_duplicate_and_invalid_layout_refused(names):
    with pytest.raises(BackupError, match="unexpected_public_tables"):
        pg.validated_tables(names)


def service_connection(broken=None):
    connection = MagicMock()
    def execute(query, parameters=None):
        if query.startswith("SELECT relname,"):
            rows = [("service_member_bindings", "schema_owner"), ("service_sessions", "schema_owner")]
            if broken == "owner": rows[0] = ("service_member_bindings", "app_user")
            return MagicMock(fetchall=lambda: rows)
        if "has_table_privilege" in query:
            role, table, privilege = parameters
            permitted = {"backup_user": {"SELECT"}, "app_user": {"SELECT", "INSERT", "DELETE"} if table.endswith("sessions") else {"SELECT"}}
            if table.endswith("bindings"): permitted["admin_user"] = {"SELECT", "INSERT", "UPDATE", "DELETE"}
            allowed = privilege in permitted.get(role, set())
            if broken == "grant" and role == "backup_user" and privilege == "UPDATE": allowed = True
            return MagicMock(fetchone=lambda: (allowed,))
        if "has_any_column_privilege" in query:
            return MagicMock(fetchone=lambda: (broken == "column_grant",))
        if "aclexplode" in query: result = (broken == "public" or (broken == "sequence_public" and "service_legacy_id_seq" in query),)
        elif "FROM pg_sequence" in query: result = None if broken == "sequence_missing" else ("schema_owner", 1, broken == "cycle")
        elif "SELECT last_value" in query: result = (17 if broken == "sequence_stale" else 18, False)
        elif "max(legacy_row_id)" in query: result = (17,)
        elif "has_sequence_privilege" in query:
            result = (tuple(parameters) in {("app_user", "USAGE"), ("backup_user", "SELECT")} or (broken == "sequence_grant" and parameters == ("app_user", "UPDATE")),)
        else: raise AssertionError("Unexpected metadata query")
        return MagicMock(fetchone=lambda: result)
    connection.execute.side_effect = execute
    return connection


def test_service_grants_ownership_and_next_locator_are_validated():
    assert all(pg.check_service_schema(service_connection()).values())


@pytest.mark.parametrize("broken", ["owner", "grant", "column_grant", "public", "sequence_missing", "cycle", "sequence_stale", "sequence_grant", "sequence_public"])
def test_unsafe_service_metadata_is_rejected(broken):
    with pytest.raises(BackupError, match="service_schema_validation_failed"):
        pg.check_service_schema(service_connection(broken))


def test_publish_checks_identity_and_marks_service_only_in_same_transaction(monkeypatch):
    marker = "dpr-backup-v1:00000000-0000-4000-8000-000000000000"
    created = {"name": "dpr_restore_"+"0"*32, "oid": 123, "marker": marker}
    connection = MagicMock()
    connection.execute.return_value.fetchone.return_value = (123, marker)
    monkeypatch.setattr(pg.psycopg, "connect", lambda **kw: connection)
    connection.__enter__.return_value = connection
    published = pg.allow_runtime_connections({"dbname": created["name"]}, created, service=True)
    assert published["marker"] == marker.replace("dpr-backup-v1:", "dpr-service-restore-v1:")
    assert len(connection.execute.call_args_list) == 3
    connection.reset_mock()
    assert pg.allow_runtime_connections({"dbname": created["name"]}, created) == created
    connection.reset_mock()
    connection.execute.return_value.fetchone.return_value = (456, marker)
    with pytest.raises(BackupError, match="restore_database_identity_changed"):
        pg.allow_runtime_connections({"dbname": created["name"]}, created)
    assert connection.execute.call_count == 1


def test_restore_requires_hba_rejection_before_creating_any_database(tmp_path, monkeypatch):
    from uuid import uuid4
    from scripts.backup import runner
    identity = str(uuid4())
    artifact = tmp_path/(identity+".dprbak"); artifact.write_bytes(b"invented encrypted fixture")
    monkeypatch.setattr(runner, "inspect_manifest", lambda *args: {"artifact_id":identity,"sha256":"checked","size_bytes":26})
    monkeypatch.setattr(runner, "file_digest", lambda stream: ("checked",26))
    monkeypatch.setattr(runner, "decrypt_stream", lambda *args: None)
    monkeypatch.setattr(runner, "plaintext_rejected", lambda *args: False)
    create = MagicMock(); monkeypatch.setattr(runner,"create_database",create)
    with pytest.raises(BackupError,match="restore_database_tls_policy_required"):
        runner.restore(tmp_path/(identity+".manifest.json"),{"host":"localhost","port":5433},(os.urandom(32),os.urandom(32)))
    create.assert_not_called()


@pytest.mark.parametrize("upgrade_fails", [False, True])
def test_restore_hardens_old_analyst_acl_before_publishing_connect(tmp_path,monkeypatch,upgrade_fails):
    from contextlib import contextmanager
    from uuid import uuid4
    from infra.protected import analyst
    from scripts.backup import runner
    identity=str(uuid4()); name="dpr_restore_"+"a"*32
    (tmp_path/(identity+".dprbak")).write_bytes(b"invented encrypted archive")
    counts={"anggota_protected":17}
    payload={"artifact_id":identity,"sha256":"verified","size_bytes":26,"table_rows":counts,
        "source_database":"protected_734","source_rows":17,"backup_seconds":1}
    monkeypatch.setattr(runner,"inspect_manifest",lambda *a:payload)
    monkeypatch.setattr(runner,"file_digest",lambda *a:("verified",26))
    monkeypatch.setattr(runner,"decrypt_stream",lambda *a:None)
    monkeypatch.setattr(runner,"plaintext_rejected",lambda *a:True)
    monkeypatch.setattr(runner,"create_database",lambda *a:{"name":name,"oid":123,"marker":"invented"})
    monkeypatch.setattr(runner,"check_server",lambda *a:None)
    monkeypatch.setattr(runner,"row_counts",lambda *a:counts)
    connection=MagicMock();connection.__enter__.return_value=connection
    monkeypatch.setattr(runner.psycopg,"connect",lambda **kw:connection)
    class Tools:
        def __init__(self,*a): pass
        def __enter__(self): return self
        def __exit__(self,*a): pass
        def bind(self): pass
        @contextmanager
        def process(self,*a): yield MagicMock()
    monkeypatch.setattr(runner,"Tools",Tools)
    events=[]
    def upgrade(value):
        events.append("upgrade")
        if upgrade_fails: raise ValueError("unsafe old ACL")
    monkeypatch.setattr(analyst,"upgrade",upgrade)
    def check(*a,**kw):
        assert events==["upgrade"]
        events.append("security_checked")
        return {"analyst_safe":True}
    monkeypatch.setattr(runner,"check_restored_security",check)
    def publish(parameters,created,**kwargs):
        assert events==["upgrade","security_checked"]
        events.append("published")
        return created
    monkeypatch.setattr(runner,"allow_runtime_connections",publish)
    cleanup=MagicMock();monkeypatch.setattr(runner,"drop_created_database",cleanup)
    arguments=(tmp_path/"manifest.json",{"host":"localhost","port":5433},(os.urandom(32),os.urandom(32)))
    if upgrade_fails:
        with pytest.raises(ValueError): runner.restore(*arguments)
        assert events==["upgrade"]
        cleanup.assert_called_once()
    else:
        assert runner.restore(*arguments)["passed"]
        assert events[-1]=="published"
        cleanup.assert_not_called()
