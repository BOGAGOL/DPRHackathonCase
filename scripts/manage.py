"""Privileged, offline provisioning/import tooling. Never imported by the web service."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api"))

from dotenv import load_dotenv
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.crypto import build_protection
from app.ingestion import baseline_members, import_baseline, load_rows, protect_rows, verify_rows
from app.main import PASSWORDS
from app.models import Assignment, Member, User


def provision(session, output):
    if session.scalar(select(User.id).limit(1)):
        raise ValueError("Users already exist; refusing to replace credentials")
    ids = list(session.scalars(select(Member.id).order_by(Member.id)))
    if not ids:
        raise ValueError("Import members first")
    specs = [("viewer.demo", "public", [], []),
             ("operator.demo", "operator", ["search:ktp", "write:contact"], ids[:12]),
             ("staff.demo", "staff", ["search:ktp", "read:identity", "read:contact", "read:address", "write:contact", "write:address"], ids[:36]),
             ("admin.demo", "admin", ["users:manage", "audit:read"], [])]
    accounts = []
    # Exclusive file first prevents a committed provisioning without retrievable passwords.
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as f:
        os.chmod(output, 0o600)
        for username, role, permissions, assignments in specs:
            password = secrets.token_urlsafe(20)
            user = User(username=username, role=role, permissions=permissions, password_hash=PASSWORDS.hash(password))
            session.add(user)
            session.flush()
            session.add_all([Assignment(user_id=user.id, member_id=i) for i in assignments])
            accounts.append({"username": username, "password": password, "role": role})
        json.dump(accounts, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
        session.commit()
    print("Demo accounts provisioned. Credentials written only to the requested local file.")


def main():
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["import", "verify", "provision", "grants", "rekey"])
    parser.add_argument("--source", type=Path)
    parser.add_argument("--expected-count", type=int, default=734)
    parser.add_argument("--credentials", type=Path, default=ROOT / ".local/demo-accounts.json")
    parser.add_argument("--evidence", type=Path, default=ROOT / "evidence/migration.json")
    args = parser.parse_args()
    settings = Settings.from_env()
    engine = create_engine(os.getenv("MIGRATION_DATABASE_URL") or settings.database_url, hide_parameters=True)
    protection = build_protection(settings)
    with Session(engine) as session:
        if args.command == "provision":
            provision(session, args.credentials)
        elif args.command == "grants":
            from psycopg import connect, sql
            from sqlalchemy.engine import make_url
            url = make_url(os.environ["MIGRATION_DATABASE_URL"])
            with connect(host=url.host, port=url.port, dbname=url.database, user=url.username, password=url.password, connect_timeout=5) as connection:
                # Password is composed with psycopg's literal quoting; never shell interpolated.
                with connection.cursor() as cursor:
                    if not cursor.execute("SELECT 1 FROM pg_roles WHERE rolname='app_user'").fetchone():
                        cursor.execute(sql.SQL("CREATE ROLE app_user LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS").format(sql.Literal(os.environ["APP_DB_PASSWORD"])))
                    cursor.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
                    cursor.execute("GRANT USAGE ON SCHEMA public TO app_user")
                    cursor.execute("GRANT SELECT ON members TO app_user")
                    cursor.execute("GRANT UPDATE (protected_fields, revision) ON members TO app_user")
                    cursor.execute("GRANT SELECT, INSERT, UPDATE ON users TO app_user")
                    cursor.execute("GRANT SELECT, INSERT, DELETE ON sessions, assignments TO app_user")
                    cursor.execute("GRANT SELECT, INSERT ON audit_events TO app_user")
                    cursor.execute("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM app_user")
                    cursor.execute("GRANT USAGE, SELECT ON SEQUENCE users_id_seq, assignments_id_seq, audit_events_id_seq TO app_user")
                    cursor.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(url.database)))
                    cursor.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO app_user").format(sql.Identifier(url.database)))
            print("Runtime grants applied; no DDL, member insert/delete, or audit update/delete granted.")
        elif args.command == "rekey":
            # Same provider, current active key. Retain old key versions until backups age out.
            for member in session.scalars(select(Member).order_by(Member.id)):
                member.protected_fields = {field: protection.encrypt(member.id, field, protection.decrypt(member.id, field, value))
                                           for field, value in member.protected_fields.items()}
            session.commit()
            print("Re-encryption committed atomically. Verify source equality and backup recovery next.")
        else:
            if not args.source:
                parser.error("--source is required")
            rows = load_rows(args.source, args.expected_count)
            checksum = hashlib.sha256(args.source.read_bytes()).hexdigest()
            if args.command == "import":
                baseline_url = os.environ["BASELINE_DATABASE_URL"]
                from sqlalchemy.engine import make_url
                baseline_config = make_url(baseline_url)
                owner_config = make_url(os.getenv("MIGRATION_DATABASE_URL") or settings.database_url)
                if (baseline_config.database == owner_config.database or baseline_config.username == owner_config.username
                    or baseline_config.password == owner_config.password
                    or (baseline_config.host, baseline_config.port) == (owner_config.host, owner_config.port)):
                    raise ValueError("Baseline requires a separate server, database and unique credentials")
                baseline = create_engine(baseline_url, hide_parameters=True)
                import_baseline(baseline, rows)
                with baseline.connect() as connection:
                    source = list(connection.execute(select(baseline_members.c.source).order_by(baseline_members.c.id)).scalars())
                protect_rows(session, protection, source, checksum)
            result = verify_rows(session, protection, rows)
            result.update(source_sha256=checksum, status="TESTED", engine=engine.dialect.name)
            args.evidence.parent.mkdir(parents=True, exist_ok=True)
            args.evidence.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Deliberately no exception repr, SQL params or traceback from migration tooling.
        print(f"Operation failed ({type(exc).__name__}); no source values logged.", file=sys.stderr)
        sys.exit(1)
