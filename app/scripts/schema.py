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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", choices=["baseline_100k", "protected_100k", "protected_734"], required=True)
    args = parser.parse_args()
    url = make_url(os.environ["APP_SETUP_DATABASE_URL"])
    if url.database != args.database or url.query.get("sslmode") != "verify-full" or not url.query.get("sslrootcert"):
        raise ValueError("Setup requires the explicit authorized database and verify-full TLS")
    # Role creation and source/protected RLS policies belong to A; never grant broader roles here.
    engine = create_engine(url, hide_parameters=True)
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
        if args.database == "baseline_100k":
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
