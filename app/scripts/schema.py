"""Provision only Module B control tables/grants; never create/drop a source or data table."""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app/backend"))
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from psycopg import sql
import psycopg
from service_app.models import AuditLog, Session, User
from service_app.protected_control import ProtectedSession, bindings
from service_app.config import Settings
from service_app.benchmark_target import benchmark_setup_url, prepare_benchmark_target


def setup_protected(engine):
    # A owns app_users/access_scope/audit_log. B adds only session/binding/ID allocation objects.
    with engine.begin() as db:
        for name in ("app_users", "access_scope", "audit_log", "anggota_protected"):
            if not db.scalar(text("SELECT to_regclass(:name)"), {"name": "public." + name}):
                raise ValueError("Apply Module A schema before service setup")
        for table in (ProtectedSession.__table__, bindings):
            table.create(db, checkfirst=True)
        for statement in (
            "ALTER TABLE service_sessions OWNER TO schema_owner",
            "ALTER TABLE service_member_bindings OWNER TO schema_owner",
            "REVOKE ALL ON service_sessions,service_member_bindings FROM PUBLIC",
            "GRANT SELECT,INSERT,DELETE ON service_sessions TO app_user",
            "GRANT SELECT ON service_member_bindings TO app_user",
            "GRANT SELECT,INSERT,UPDATE,DELETE ON service_member_bindings TO admin_user",
            "GRANT SELECT ON service_sessions,service_member_bindings TO backup_user"):
            db.execute(text(statement))
        if not db.scalar(text("SELECT to_regclass('public.service_legacy_id_seq')")):
            # Trusted setup sees every row; runtime RLS may only expose a subset.
            maximum = db.scalar(text("SELECT coalesce(max(legacy_row_id),0) FROM anggota_protected"))
            db.execute(text("CREATE SEQUENCE service_legacy_id_seq"))
            db.execute(text("SELECT setval('service_legacy_id_seq', :next, false)"), {"next": maximum + 1})
            db.execute(text("ALTER SEQUENCE service_legacy_id_seq OWNER TO schema_owner"))
        db.execute(text("GRANT USAGE ON SEQUENCE service_legacy_id_seq TO app_user"))
        db.execute(text("GRANT SELECT ON SEQUENCE service_legacy_id_seq TO backup_user"))


def main():
    benchmark = Settings.from_env() if os.getenv("DPR_BENCHMARK_DATABASE") else None
    allowed = ["baseline_100k", "baseline_1m", "protected_100k", "protected_734", "protected_1m"]
    if benchmark:
        allowed = [benchmark.benchmark_database]
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", choices=allowed, required=True)
    args = parser.parse_args()
    url = make_url(os.environ["APP_SETUP_DATABASE_URL"])
    if url.database != args.database or url.query.get("sslmode") != "verify-full" or not url.query.get("sslrootcert"):
        raise ValueError("Setup requires the explicit authorized database and verify-full TLS")
    if benchmark:
        url = benchmark_setup_url(benchmark, os.environ["APP_SETUP_DATABASE_URL"])
    # Role creation and source/protected RLS policies belong to A; never grant broader roles here.
    engine = create_engine(url, hide_parameters=True)
    if benchmark:
        try:
            prepare_benchmark_target(engine, benchmark)
        except Exception:
            engine.dispose()
            raise
    protected = benchmark.mode == "protected" if benchmark else args.database.startswith("protected_")
    if protected:
        setup_protected(engine)
        engine.dispose()
        print("Module B protected session/binding/locator objects ready; A accounts/audit/RLS retained.")
        return
    for model in [User, Session, AuditLog]:
        model.__table__.create(engine, checkfirst=True)
    with engine.begin() as connection:
        for statement in ["GRANT SELECT, INSERT, UPDATE ON users TO app_user",
                          "GRANT SELECT, INSERT, DELETE ON sessions TO app_user",
                          "GRANT SELECT, INSERT ON audit_log TO app_user",
                          "GRANT USAGE, SELECT ON SEQUENCE audit_log_id_seq TO app_user",
                          "GRANT SELECT ON audit_log TO auditor_user"]:
            connection.execute(text(statement))
        # Baseline table exists and belongs to C; only its approved service grants are added.
        if args.database in {"baseline_100k", "baseline_1m"} or benchmark:
            connection.execute(text("GRANT SELECT, INSERT, UPDATE ON anggota TO app_user"))
            sequence = connection.execute(text("SELECT c.oid FROM pg_class c WHERE c.oid=pg_get_serial_sequence('anggota','id')::regclass")).scalar()
            if sequence:
                # Resolve identifiers via catalog, never interpolate an untrusted sequence name.
                schema_name, sequence_name = connection.execute(text("SELECT n.nspname,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.oid=:oid"), {"oid": sequence}).one()
                raw = connection.connection.driver_connection
                with raw.cursor() as cursor:
                    cursor.execute(sql.SQL("GRANT USAGE, SELECT ON SEQUENCE {}.{} TO app_user").format(sql.Identifier(schema_name), sql.Identifier(sequence_name)))
    engine.dispose()
    print("Module B control schema/grants ready; dataset rows and Module A policies unchanged.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Setup failed ({type(exc).__name__}); credentials/SQL values withheld.", file=sys.stderr)
        sys.exit(1)
