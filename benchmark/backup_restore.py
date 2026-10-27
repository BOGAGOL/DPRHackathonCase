"""PG18 custom dumps + restore into exclusively new, guarded disposable databases."""

import json
from pathlib import Path
import re
import statistics
import subprocess
import time
from uuid import uuid4

import psycopg
from psycopg import sql

from datagen.database import provenance, source_rows
from datagen.model import checksum
from .common import RAW, EVIDENCE, parameters, private_directory, state, same_data, utc_now, write_json, write_csv, file_hash, running_containers


def guard_restore(name):
    if not re.fullmatch(r"bench_restore_[1-9][0-9]*_[0-9a-f]{12}", name):
        raise ValueError("Only this runner's disposable restore names allowed")
    return name


def backup_restore(runs=3, keep=False):
    if runs < 3:
        raise ValueError("At least three backup/restore runs required")
    if (RAW / "backup_restore/runs.csv").exists():
        raise ValueError("Existing backup session; refusing overwrite")
    if running_containers() != ["pg-dpr"]:
        raise ValueError("Expected only pg-dpr running")
    before = state()
    original = checksum(source_rows())
    rows = []
    for run in range(1, runs + 1):
        name = guard_restore(f"bench_restore_{run}_{uuid4().hex[:12]}")
        path = private_directory() / (name + ".dump")
        row = {"run": run, "temporary_database": name, "status": "FAILED", "started_at_utc": utc_now()}
        try:
            started = time.perf_counter()
            with path.open("xb") as handle:
                subprocess.run(["docker", "exec", "pg-dpr", "pg_dump", "-U", "postgres", "-Fc", "--no-owner", "--no-acl",
                                "--dbname", "baseline_100k"], stdout=handle, stderr=subprocess.PIPE, check=True)
            row.update(backup_s=time.perf_counter() - started, dump_bytes=path.stat().st_size)
            started = time.perf_counter()
            with psycopg.connect(**parameters("postgres", admin=True), autocommit=True) as admin:
                admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0 ENCODING 'UTF8'").format(sql.Identifier(name)))
            with path.open("rb") as handle:
                subprocess.run(["docker", "exec", "-i", "pg-dpr", "pg_restore", "-U", "postgres", "--exit-on-error",
                                "--single-transaction", "--no-owner", "--no-acl", "--dbname", name], stdin=handle,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
            row["restore_s"] = time.perf_counter() - started
            verified = state(name, admin=True)
            row.update(restored_rows=verified["rows"], checksum_matches=before["checksum_sha256"] == verified["checksum_sha256"],
                       sequence_matches=before["sequence"] == verified["sequence"], dump_sha256=file_hash(path))
            if not same_data(before, verified):
                raise ValueError("Restored content mismatch; own failed database retained")
            with psycopg.connect(**parameters("postgres", admin=True), autocommit=True) as admin:
                admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(guard_restore(name))))
            row.update(status="PASSED", temporary_database_removed=True)
            if not keep:
                path.unlink()  # Exact private file exclusively created by this run.
            row["dump_retained_private"] = keep
        except Exception:
            rows.append(row)
            write_json(RAW / "backup_restore/failure.json", {"status": "FAILED", "runs": rows})
            write_json(EVIDENCE / "backup_restore.json", {"status": "FAILED", "runs": rows})
            raise
        rows.append(row)
        print(json.dumps({"phase": "backup_restore_finished", "run": run,
                          "backup_s": row["backup_s"], "restore_s": row["restore_s"], "rows": row["restored_rows"]}), flush=True)
    after = state()
    source_unchanged = original == checksum(source_rows())
    report = {"status": "PASSED" if same_data(before, after) and source_unchanged else "FAILED",
              "session_kind": "baseline_awal", "database": "baseline_100k", "endpoint": "pg-dpr:5433",
              "level": "DB", "runs": rows, "medians": {k: statistics.median(r[k] for r in rows)
                                                       for k in ("backup_s", "restore_s", "dump_bytes")},
              "baseline_data_and_sequence_unchanged": same_data(before, after), "source_database_unchanged": source_unchanged,
              "source_checksum_sha256": original, "baseline_checksum_sha256": before["checksum_sha256"],
              "format": "pg_dump -Fc", "client": "container PostgreSQL 18", "encryption": "none (initial plaintext baseline)",
              "transport": "container Unix socket, no TLS", "backup_boundary": "Docker exec + pg_dump + writing private custom archive",
              "restore_boundary": "CREATE new database + Docker exec + pg_restore; validation and cleanup excluded",
              "completed_at_utc": utc_now(), **provenance()}
    for directory in (RAW, EVIDENCE):
        write_json(directory / "backup_restore.json", report)
        write_csv(directory / "backup_restore/runs.csv", rows)
    return report
