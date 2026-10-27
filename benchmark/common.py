"""Safe environment, dataset guards and output helpers."""

from datetime import datetime, timezone
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
import re

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg import sql

from datagen.model import COLUMNS, checksum

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "results/bench/before"
EVIDENCE = ROOT / "evidence/benchmark/baseline"
BASELINE_ROWS = {"baseline_100k": 100000, "baseline_1m": 1000000}


def replacement_paths(session):
    if not re.fullmatch(r"ac_[0-9]{8}T[0-9]{6}Z", session):
        raise ValueError("Invalid AC replacement session name")
    return ROOT / "results/bench/replacements" / session, ROOT / "evidence/benchmark/replacements" / session


def session_paths(database):
    if database not in BASELINE_ROWS:
        raise ValueError("Baseline dataset not authorized")
    return ((RAW, EVIDENCE) if database == "baseline_100k" else
            (ROOT / "results/bench/before_1m", ROOT / "evidence/benchmark/baseline_1m"))


def require_disk_space(path=ROOT, minimum_bytes=10_000_000_000):
    free = shutil.disk_usage(path).free
    if free < minimum_bytes:
        raise ValueError("Insufficient disk space: minimum 10 GB required")
    return free


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def parameters(database="baseline_100k", admin=False):
    variable = "DATAGEN_DATABASE_URL" if admin else "BENCH_DATABASE_URL"
    value = os.environ.get(variable)
    if not value:
        raise ValueError("Required database environment missing")
    params = conninfo_to_dict(value)
    if (params.get("host"), params.get("port")) != ("127.0.0.1", "5433"):
        raise ValueError("Only authorized pg-dpr endpoint allowed")
    if not admin and (database not in BASELINE_ROWS or params.get("user") != "bench_user"):
        raise ValueError("Workload must use bench_user on an authorized baseline")
    if admin and database not in {"postgres", *BASELINE_ROWS} and not database.startswith("bench_restore_"):
        raise ValueError("Administrative database target denied")
    params.update(dbname=database, sslmode="disable", connect_timeout=10,
                  application_name="dpr-baseline-benchmark", options="-c statement_timeout=10000")
    return params


def private_directory():
    configured = os.environ.get("DPR_PRIVATE_DIR")
    if not configured:
        raise ValueError("DPR_PRIVATE_DIR required")
    path = Path(configured).resolve()
    if path == ROOT or path.is_relative_to(ROOT):
        raise ValueError("Private storage cannot be inside repo")
    path = path / "benchmark"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_csv(path, rows):
    if not rows:
        raise ValueError("No CSV rows")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def state(database="baseline_100k", admin=False):
    """Canonical full dataset digest, count and sequence, with a read-only snapshot."""
    with psycopg.connect(**parameters(database, admin), row_factory=dict_row) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        count = conn.execute("SELECT count(*) AS n FROM public.anggota").fetchone()["n"]
        with conn.cursor(name="benchmark_integrity") as cursor:
            cursor.execute(sql.SQL("SELECT {} FROM public.anggota ORDER BY id").format(
                sql.SQL(",").join(map(sql.Identifier, COLUMNS))))
            digest = checksum(cursor)
        seq = conn.execute("SELECT last_value,is_called FROM public.anggota_id_seq").fetchone()
        sizes = conn.execute("SELECT pg_database_size(current_database()) AS database_bytes, "
            "pg_relation_size('public.anggota') AS heap_bytes, pg_table_size('public.anggota') AS table_bytes, "
            "pg_indexes_size('public.anggota') AS index_bytes").fetchone()
    return {"rows": count, "checksum_sha256": digest, "sequence": seq, "storage": sizes}


def same_data(first, second):
    return all(first[k] == second[k] for k in ("rows", "checksum_sha256", "sequence"))


def running_containers():
    result = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True, check=True)
    return sorted(result.stdout.split())
