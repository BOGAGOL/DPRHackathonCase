"""Explicit operator-selected benchmark clone; no creation, rename or recovery."""
from pathlib import Path

from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import make_url


def benchmark_setup_url(settings, value):
    settings.validate()
    runtime, setup = make_url(settings.database_url), make_url(value)
    if (not settings.benchmark_database or setup.get_backend_name() != "postgresql"
            or setup.username != "postgres"
            or (setup.host, setup.port, setup.database) != (runtime.host, runtime.port, settings.benchmark_database)
            or setup.query.get("sslmode") != "verify-full"
            or not Path(setup.query.get("sslrootcert", "")).is_file()):
        raise ValueError("Benchmark setup requires the same explicit clone and verified admin TLS")
    return setup


def prepare_benchmark_target(engine, settings):
    """Trusted setup grants only runtime connection/schema usage on its own clone."""
    with engine.begin() as connection:
        state = connection.execute(text("SELECT current_database(),(SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid())")).one()
        if tuple(state) != (settings.benchmark_database, True):
            raise ValueError("Benchmark setup connected to another target or without TLS")
        member_table = "public.anggota_protected" if settings.mode == "protected" else "public.anggota"
        if not connection.scalar(text("SELECT to_regclass(:table_name)"), {"table_name": member_table}):
            raise ValueError("Clone member schema does not match MODE")
        statements = (
            sql.SQL("GRANT CONNECT ON DATABASE {} TO app_user,analyst_user,auditor_user").format(sql.Identifier(settings.benchmark_database)),
            sql.SQL("GRANT USAGE ON SCHEMA public TO app_user,analyst_user,auditor_user"),
            sql.SQL("COMMENT ON DATABASE {} IS {}").format(sql.Identifier(settings.benchmark_database), sql.Literal("dpr-service-benchmark-v1:" + settings.mode)),
        )
        for statement in statements:
            connection.execute(text(statement.as_string()))


def verify_benchmark_target(connection, expected_database, mode):
    """Read-only startup gate. The marker declares setup, not corpus integrity."""
    connection.execute(text("SET TRANSACTION READ ONLY"))
    state = connection.execute(text("SELECT current_database(),current_user,(SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()),shobj_description(d.oid,'pg_database'),r.rolsuper OR r.rolbypassrls OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication OR EXISTS(SELECT 1 FROM pg_auth_members WHERE member=r.oid),has_schema_privilege(current_user,'public','CREATE') FROM pg_database d JOIN pg_roles r ON r.rolname=current_user WHERE d.datname=current_database()")).one()
    if tuple(state) != (expected_database, "app_user", True, "dpr-service-benchmark-v1:" + mode, False, False):
        raise ValueError("Verified benchmark clone required")
    required = (["anggota", "users", "sessions", "audit_log"] if mode == "plain" else
                ["anggota_protected", "app_users", "access_scope", "audit_log", "migration_jobs", "service_member_bindings", "service_sessions"])
    for table in required:
        if not connection.scalar(text("SELECT to_regclass(:table_name)"), {"table_name": "public." + table}):
            raise ValueError("Benchmark service schema incomplete")
    if mode == "protected":
        protected = connection.execute(text("SELECT pg_get_userbyid(relowner),relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid='public.anggota_protected'::regclass")).one()
        if tuple(protected) != ("schema_owner", True, True):
            raise ValueError("Benchmark protected ownership/RLS required")
