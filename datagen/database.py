"""Guarded PostgreSQL operations; credentials only from process environment."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import hashlib

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from . import __version__
from .model import COLUMNS, generate, validate, checksum

ROOT = Path(__file__).resolve().parents[1]


def guard_target(name):
    if not re.fullmatch(r"baseline_[a-z0-9_]{1,50}", name):
        raise ValueError("Only new baseline_* targets are allowed")
    return name


def parameters(database, variable="DATAGEN_DATABASE_URL"):
    value = os.environ.get(variable)
    if not value:
        raise ValueError("Required database environment missing")
    params = conninfo_to_dict(value)
    if params.get("host") != "127.0.0.1" or params.get("port") != "5433":
        raise ValueError("Expected the authorized local PostgreSQL endpoint")
    params.update(dbname=database, connect_timeout=10, application_name="dpr-datagen")
    return params


def source_rows():
    with psycopg.connect(**parameters("postgres"), row_factory=dict_row) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        if conn.info.server_version // 10000 != 18:
            raise ValueError("PostgreSQL 18 required")
        rows = conn.execute(sql.SQL("SELECT {} FROM public.anggota ORDER BY id").format(
            sql.SQL(",").join(map(sql.Identifier, COLUMNS)))).fetchall()
    if len(rows) != 734:
        raise ValueError("Expected 734 source records")
    return rows


def record(name, payload):
    """Write small machine evidence and local compatibility metadata, no row values."""
    guard_target(name)
    for parent in (ROOT / "evidence/datasets", ROOT / "results/bench/datasets"):
        parent.mkdir(parents=True, exist_ok=True)
        path = parent / (name + ".json")
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(path)


def provenance():
    targets = json.loads((ROOT / "evidence/targets_commit.json").read_text(encoding="utf-8-sig"))
    if targets.get("file") != "docs/targets.md" or not re.fullmatch("[0-9a-f]{40}", targets.get("commit", "")):
        raise ValueError("Target commit evidence invalid")
    subprocess.run(["git", "cat-file", "-e", targets["commit"] + ":docs/targets.md"],
                   cwd=ROOT, capture_output=True, check=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "datagen"], cwd=ROOT,
                                capture_output=True, text=True, check=True).stdout.strip())
    return {"generator_version": __version__, "code_commit": head, "datagen_worktree_dirty": dirty,
            "targets_commit": targets["commit"], "targets_committed_at_wib": targets["committed_at_wib"]}


def validate_database(name, total, replicate_anomalies=True):
    guard_target(name)
    source = source_rows()
    with psycopg.connect(**parameters(name), row_factory=dict_row) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        with conn.cursor(name="datagen_validation") as cursor:
            cursor.execute(sql.SQL("SELECT {} FROM public.anggota ORDER BY id").format(
                sql.SQL(",").join(map(sql.Identifier, COLUMNS))))
            result = validate(cursor, source, total, replicate_anomalies)
    return result


def build(name, total, seed=42, replicate_anomalies=True):
    guard_target(name)
    origin = provenance()
    source = source_rows()
    if total < len(source):
        raise ValueError("Target smaller than source")
    with psycopg.connect(**parameters("postgres"), autocommit=True) as admin:
        if admin.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone():
            raise ValueError("Target exists; refusing overwrite, use validate instead")
        admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0 ENCODING 'UTF8'").format(sql.Identifier(name)))
    # From this point the DB exists; failure never drops it or changes the source.
    payload = {"status": "FAILED", "database": name, "rows_requested": total, "seed": seed,
               "replicate_anomalies": replicate_anomalies,
               "created_at_utc": datetime.now(timezone.utc).isoformat(), **origin}
    try:
        with psycopg.connect(**parameters(name)) as conn:
            conn.execute((ROOT / "sql/baseline/01_schema.sql").read_text(encoding="utf-8-sig"))
            with conn.cursor().copy(sql.SQL("COPY public.anggota ({}) FROM STDIN").format(
                    sql.SQL(",").join(map(sql.Identifier, COLUMNS)))) as copy:
                for row in generate(source, total, seed, replicate_anomalies):
                    copy.write_row(tuple(row[c] for c in COLUMNS))
            conn.execute("SELECT setval(pg_get_serial_sequence(%s,%s), (SELECT max(id) FROM public.anggota), true)",
                         ("public.anggota", "id"))
            conn.execute("ANALYZE public.anggota")
        result = validate_database(name, total, replicate_anomalies)
        result["source_database_unchanged"] = checksum(source_rows()) == checksum(source)
        result["passed"] = result["passed"] and result["source_database_unchanged"]
        payload.update(status="PASSED" if result["passed"] else "FAILED", validation=result,
                       baseline_checksum_sha256=result["checksum_sha256"])
        record(name, payload)
        if not result["passed"]:
            raise ValueError("Dataset validation failed; see aggregate evidence")
        return payload
    except Exception:
        record(name, payload)
        raise


def private_path(out):
    configured = os.environ.get("DPR_PRIVATE_DIR")
    if not configured:
        raise ValueError("DPR_PRIVATE_DIR required")
    directory = Path(configured).resolve()
    if directory == ROOT or directory.is_relative_to(ROOT):
        raise ValueError("Private storage must be outside repository")
    path = Path(out).resolve()
    if path == directory or not path.is_relative_to(directory):
        raise ValueError("Snapshot must be inside DPR_PRIVATE_DIR")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def snapshot(name, out):
    guard_target(name)
    path = private_path(out)
    params = parameters(name)
    # Container PG18 client; Unix socket authentication already configured by lab owner.
    cmd = ["docker", "exec", "pg-dpr", "pg_dump", "--format=custom", "--no-owner", "--no-acl",
           "--username", params.get("user", "postgres"), "--dbname", name]
    with path.open("xb") as handle:
        try:
            subprocess.run(cmd, stdout=handle, stderr=subprocess.PIPE, check=True)
        except Exception:
            handle.close()
            path.unlink()  # Only the file exclusively created by this call.
            raise
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        if handle.read(5) != b"PGDMP":
            raise ValueError("Invalid custom snapshot")
        handle.seek(0)
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    payload_path = ROOT / "evidence/datasets" / (name + ".json")
    payload = json.loads(payload_path.read_text(encoding="utf-8")) if payload_path.exists() else {
        "database": name, **provenance()}
    payload["snapshot"] = {"format": "pg_dump_custom", "client": "pg-dpr/pg_dump18",
                           "outside_repository": True, "bytes": path.stat().st_size,
                           "sha256": digest.hexdigest(), "created_at_utc": datetime.now(timezone.utc).isoformat()}
    record(name, payload)
    return payload["snapshot"]


def provision(name):
    """Create a separate lab benchmark login, preserve existing scanner credentials."""
    guard_target(name)
    bench = parameters(name, "BENCH_DATABASE_URL")
    if bench.get("user") != "bench_user" or not bench.get("password"):
        raise ValueError("BENCH_DATABASE_URL must supply bench_user credentials")
    with psycopg.connect(**parameters(name)) as conn:
        # No password/verifier in PostgreSQL statement/error logging.
        conn.execute("SET LOCAL log_statement = 'none'")
        conn.execute("SET LOCAL log_min_duration_statement = -1")
        conn.execute("SET LOCAL log_min_error_statement = 'panic'")
        existing = conn.execute("SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls "
                                "FROM pg_roles WHERE rolname=%s", ("bench_user",)).fetchone()
        if existing and any(existing):
            raise ValueError("Existing benchmark role has unsafe privileges")
        if not existing:
            verifier = conn.pgconn.encrypt_password(bench["password"].encode(), b"bench_user", b"scram-sha-256").decode()
            conn.execute(sql.SQL("CREATE ROLE bench_user LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                                 "NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD {}").format(sql.Literal(verifier)))
        if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", ("scanner_user",)).fetchone():
            raise ValueError("scanner_user must be provisioned by its owner first")
        conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(name)))
        conn.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
        conn.execute("REVOKE ALL ON TABLE public.anggota FROM PUBLIC")
        conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO bench_user, scanner_user").format(sql.Identifier(name)))
        conn.execute("GRANT USAGE ON SCHEMA public TO bench_user, scanner_user")
        conn.execute("GRANT SELECT, INSERT, UPDATE ON public.anggota TO bench_user")
        conn.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO bench_user")
        conn.execute("GRANT SELECT ON public.anggota TO scanner_user")
        memberships = conn.execute("SELECT count(*) FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=%s)",
                                   ("bench_user",)).fetchone()[0]
        if memberships:
            raise ValueError("Existing benchmark role has unexpected memberships")
    with psycopg.connect(**bench) as conn:
        checks = {"bench_identity": conn.execute("SELECT current_user").fetchone()[0] == "bench_user",
                  "bench_read_count": conn.execute("SELECT count(*) FROM public.anggota").fetchone()[0] > 0,
                  "bench_no_schema_ddl": not conn.execute("SELECT has_schema_privilege(current_user,'public','CREATE')").fetchone()[0],
                  "bench_no_delete": not conn.execute("SELECT has_table_privilege(current_user,'public.anggota','DELETE')").fetchone()[0]}
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"):
            expected = privilege in {"SELECT", "INSERT", "UPDATE"}
            label = "bench_" + privilege.lower() + ("_allowed" if expected else "_denied")
            checks[label] = conn.execute("SELECT has_table_privilege(current_user,%s,%s)",
                                         ("public.anggota", privilege)).fetchone()[0] == expected
        checks["bench_identity_sequence_allowed"] = conn.execute(
            "SELECT has_sequence_privilege(current_user,pg_get_serial_sequence(%s,%s),'USAGE')",
            ("public.anggota", "id")).fetchone()[0]
    with psycopg.connect(**parameters(name)) as conn:
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"):
            label = "scanner_" + privilege.lower() + ("_allowed" if privilege == "SELECT" else "_denied")
            checks[label] = conn.execute(
                "SELECT has_table_privilege(%s,%s,%s)", ("scanner_user", "public.anggota", privilege)).fetchone()[0] == (privilege == "SELECT")
    # Verify no data privileges were introduced on the original DB, without changing its ACL.
    with psycopg.connect(**parameters("postgres")) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        checks["bench_no_source_select"] = not conn.execute(
            "SELECT has_table_privilege(%s,%s,%s)", ("bench_user", "public.anggota", "SELECT")).fetchone()[0]
    path = ROOT / "evidence/datasets" / (name + ".json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["roles"] = {"passed": all(checks.values()), "checks": checks,
                        "scope": "Data privileges; PUBLIC CONNECT on other databases is not modified"}
    record(name, payload)
    if not all(checks.values()):
        raise ValueError("Role validation failed")
    return payload["roles"]
