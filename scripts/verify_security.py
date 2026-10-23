"""Lab security evidence with no PII values in the output."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

from dotenv import load_dotenv
import httpx
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api"))
from app.ingestion import load_rows
from app.models import Member
from backup import pg_env


def main():
    load_dotenv(ROOT / ".env")
    source = ROOT.parent.parent / "Task1_Hackathon_DPR_2026/Task1_Hackathon_DPR_2026/anggota_dummy.sql"
    rows = load_rows(source)
    # Independent comparison against the pre-existing scanner parser (offline evidence only).
    scanner = source.parent / "task1_scanner.py"
    spec = importlib.util.spec_from_file_location("existing_task1_scanner", scanner)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    columns, independent = module.load_rows(source)
    same_source = rows == independent
    if not same_source:
        raise ValueError("Independent parsers disagree (values withheld)")
    owner = make_url(os.environ["MIGRATION_DATABASE_URL"])
    runtime = create_engine(os.environ["DATABASE_URL"], hide_parameters=True)
    checks = {}
    with runtime.connect() as db:
        checks["runtime_identity"] = db.execute(text("select current_user")).scalar() == "app_user"
        for name, table, privilege, expected in [("member_read", "members", "SELECT", True), ("member_delete_denied", "members", "DELETE", False),
                                                  ("member_insert_denied", "members", "INSERT", False), ("audit_update_denied", "audit_events", "UPDATE", False),
                                                  ("audit_delete_denied", "audit_events", "DELETE", False), ("import_metadata_denied", "import_runs", "SELECT", False)]:
            value = db.execute(text("select has_table_privilege(current_user,:table,:privilege)"), {"table": table, "privilege": privilege}).scalar()
            checks[name] = value is expected
        flags = db.execute(text("select rolsuper,rolcreatedb,rolcreaterole,rolbypassrls from pg_roles where rolname=current_user")).one()
        checks["no_superuser_or_ddl_roles"] = not any(flags)
        schema = db.execute(text("select has_schema_privilege(current_user,'public','CREATE')")).scalar()
        checks["no_schema_creation"] = not schema
        checks["encrypted_field_count"] = len(db.execute(select(Member.protected_fields).limit(1)).scalar_one()) == 27
    import shutil
    dump = subprocess.run([shutil.which("pg_dump") or "pg_dump", "--format=plain", "--no-owner", "--no-acl", "--dbname", owner.database],
                          env=pg_env(owner), capture_output=True, check=True).stdout
    forbidden = [r[f].encode() for r in rows for f in ["no_ktp", "rekening", "email", "handphone"] if r[f]]
    checks["logical_dump_no_sensitive_canaries"] = not any(value in dump for value in forbidden)
    import base64
    keys = list(json.loads(os.environ["ENCRYPTION_KEYS"]).values()) + [os.environ["BLIND_INDEX_KEY"]]
    checks["logical_dump_no_keys"] = not any(value.encode() in dump for value in keys)
    checks["independent_parser_equality"] = same_source
    accounts = json.loads((ROOT / ".local/demo-accounts.json").read_text())
    with httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False) as client:
        checks["live_unauthenticated_denied"] = client.get("/anggota").status_code == 401
        for account in accounts:
            client.cookies.clear()
            client.get("/auth/csrf")
            response = client.post("/auth/login", headers={"X-CSRF-Token": client.cookies["dpr_csrf"]},
                                   json={"username": account["username"], "password": account["password"]})
            checks[f"live_login_{account['role']}"] = response.status_code == 200
            detail = client.get("/anggota/1")
            role = account["role"]
            checks[f"live_role_{role}"] = ((detail.status_code == 404) if role == "admin" else
                                            (detail.status_code == 200 and "rekening" not in detail.json()["fields"]))
            if role == "public":
                injected = client.get("/anggota", params={"q": "' OR 1=1 --"})
                checks["live_postgres_injection_literal"] = injected.status_code == 200 and injected.json()["total"] == 0
    # Check keys and credentials against Git's nonignored project file list, without staging anything.
    paths = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT, capture_output=True, check=True).stdout.decode().split("\x00")
    needles = [k.encode() for k in keys] + [a["password"].encode() for a in accounts]
    checks["repository_no_current_secrets"] = not any(any(n in (ROOT / p).read_bytes() for n in needles) for p in paths if p and (ROOT / p).is_file())
    checks["git_ignores_env"] = subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=ROOT).returncode == 0
    report = {"status": "TESTED" if all(checks.values()) else "FAILED", "checks": checks,
              "scope": "PostgreSQL lab + live FastAPI, synthetic canaries only. Physical file/WAL encryption not assessed."}
    (ROOT / "evidence/postgres-security.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Security verification failed ({type(exc).__name__}); values withheld.", file=sys.stderr)
        sys.exit(1)
