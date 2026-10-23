"""Comparable DB business workload. No API/TLS performance claims from this runner."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import random
import statistics
import sys
import time

import psutil
from dotenv import load_dotenv
from sqlalchemy import create_engine, select, text, update
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api"))
from app.config import Settings
from app.crypto import build_protection
from app.ingestion import baseline_members
from app.models import Member
from backup import decrypt_dump, dump_database, encrypt_dump, restore_new
from sqlalchemy.engine import make_url


def db_processes(mode):
    path = ROOT / ".local" / f"pg-{mode}" / "postmaster.pid"
    if not path.exists():
        return []
    process = psutil.Process(int(path.read_text().splitlines()[0]))
    return [process, *process.children(recursive=True)]


def resources(processes):
    cpu, ram = 0, 0
    for process in processes:
        try:
            times = process.cpu_times()
            cpu += times.user + times.system
            ram += process.memory_info().rss
        except psutil.NoSuchProcess:
            pass
    return cpu, ram


def percentile(values, p):
    s = sorted(values)
    return s[min(len(s)-1, max(0, int((len(s)-1)*p)))]


def main():
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--operations", type=int, default=300)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, default=ROOT / "evidence/benchmark.json")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--backup-restore", action="store_true", help="Repeat encrypted backup + restore for both configurations")
    args = parser.parse_args()
    if args.env_file:
        load_dotenv(args.env_file, override=True)
    if args.repeats < 3 or args.operations < 30:
        parser.error("At least three repeats and 30 operations required")
    settings = Settings.from_env()
    protection = build_protection(settings)
    engines = {"baseline": create_engine(os.environ["BASELINE_DATABASE_URL"], hide_parameters=True),
               "protected": create_engine(os.environ["MIGRATION_DATABASE_URL"], hide_parameters=True)}
    with engines["baseline"].connect() as connection:
        source = {r.id: r.source for r in connection.execute(select(baseline_members))}
    with Session(engines["protected"]) as db:
        protected = {m.id: dict(m.protected_fields) for m in db.scalars(select(Member))}
    if set(source) != set(protected) or not source:
        raise ValueError("Datasets must contain identical IDs and counts")
    ids = sorted(source)
    rng = random.Random(2026)
    workload = [(rng.choice(ids), "write" if i % 5 == 0 else "read") for i in range(args.operations)]
    process = psutil.Process()
    results = []
    backup_key = os.urandom(32)
    try:
        # Alternate order each repetition to reduce systematic cache/order bias.
        for repetition in range(args.repeats):
            for mode in (["baseline", "protected"] if repetition % 2 == 0 else ["protected", "baseline"]):
                engine = engines[mode]
                samples, errors, crypto_samples, memory = [], 0, [], []
                # Same warmup count and read workload.
                with engine.connect() as connection:
                    for identifier in ids[:20]:
                        connection.execute(select(Member.__table__ if mode == "protected" else baseline_members).where(
                            Member.id == identifier if mode == "protected" else baseline_members.c.id == identifier)).first()
                db_procs = db_processes(mode)
                db_cpu_before, _ = resources(db_procs)
                db_ram = []
                cpu_before = process.cpu_times()
                start = time.perf_counter()
                for identifier, operation in workload:
                    op_start = time.perf_counter()
                    try:
                        with engine.begin() as connection:
                            if mode == "baseline":
                                payload = connection.execute(select(baseline_members.c.source).where(baseline_members.c.id == identifier)).scalar_one()
                                if operation == "write":
                                    payload = {**payload, "email": "benchmark@example.test"}
                                    connection.execute(update(baseline_members).where(baseline_members.c.id == identifier).values(source=payload))
                                result = {f: payload[f] for f in ["email", "handphone"]}
                            else:
                                payload = connection.execute(select(Member.protected_fields).where(Member.id == identifier)).scalar_one()
                                c_start = time.perf_counter()
                                if operation == "write":
                                    payload = {**payload, "email": protection.encrypt(identifier, "email", "benchmark@example.test")}
                                result = {f: protection.decrypt(identifier, f, payload[f]) for f in ["email", "handphone"]}
                                crypto_samples.append((time.perf_counter()-c_start)*1000)
                                if operation == "write":
                                    connection.execute(update(Member).where(Member.id == identifier).values(protected_fields=payload))
                            if set(result) != {"email", "handphone"}:
                                raise ValueError("Business output mismatch")
                    except Exception:
                        errors += 1
                    samples.append({"operation": operation, "duration_ms": (time.perf_counter()-op_start)*1000})
                    memory.append(process.memory_info().rss)
                    db_ram.append(resources(db_procs)[1])
                elapsed = time.perf_counter()-start
                cpu_after = process.cpu_times()
                db_cpu_after, _ = resources(db_procs)
                durations = [s["duration_ms"] for s in samples]
                with engine.connect() as connection:
                    storage = connection.execute(text("SELECT pg_database_size(current_database())")).scalar_one()
                results.append({"mode": mode, "repetition": repetition+1, "operations": len(samples), "errors": errors,
                                "error_rate": errors/len(samples), "p50_ms": percentile(durations, .5), "p95_ms": percentile(durations, .95),
                                "throughput_success_ops_s": (len(samples)-errors)/elapsed,
                                "runner_cpu_percent_one_core": ((cpu_after.user+cpu_after.system)-(cpu_before.user+cpu_before.system))/elapsed*100,
                                "runner_peak_rss_bytes": max(memory), "database_bytes": storage,
                                "db_cpu_percent_one_core": (db_cpu_after-db_cpu_before)/elapsed*100 if db_procs else None,
                                "db_peak_rss_sum_bytes": max(db_ram) if db_procs else None,
                                "crypto_mean_ms": statistics.mean(crypto_samples) if crypto_samples else None,
                                "samples": samples})
    finally:
        # Restore the exact source payloads/ciphertexts, even if the runner fails.
        with engines["baseline"].begin() as connection:
            for identifier, payload in source.items():
                connection.execute(update(baseline_members).where(baseline_members.c.id == identifier).values(source=payload))
        with engines["protected"].begin() as connection:
            for identifier, payload in protected.items():
                connection.execute(update(Member).where(Member.id == identifier).values(protected_fields=payload))
    backup_results = []
    if args.backup_restore:
        for repetition in range(args.repeats):
            for mode, engine in engines.items():
                start = time.perf_counter()
                data = encrypt_dump(dump_database(engine.url), backup_key)
                backup_seconds = time.perf_counter()-start
                start = time.perf_counter()
                restored_name = restore_new(engine.url, decrypt_dump(data, backup_key))
                restore_seconds = time.perf_counter()-start
                restored = create_engine(engine.url.set(database=restored_name), hide_parameters=True)
                with restored.connect() as connection:
                    count = connection.execute(text("select count(*) from members" if mode == "protected" else "select count(*) from baseline_members")).scalar_one()
                restored.dispose()
                if count != len(ids):
                    raise ValueError("Restored count mismatch")
                backup_results.append({"mode": mode, "repetition": repetition+1, "backup_seconds": backup_seconds,
                                       "restore_seconds": restore_seconds, "encrypted_bytes": len(data), "records_verified": count,
                                       "restored_database": restored_name})
    summary = {}
    for mode in engines:
        subset = [r for r in results if r["mode"] == mode]
        summary[mode] = {k: statistics.median(r[k] for r in subset) for k in ["p50_ms", "p95_ms", "throughput_success_ops_s", "error_rate", "runner_cpu_percent_one_core", "runner_peak_rss_bytes", "database_bytes"]}
        if subset and subset[0]["db_cpu_percent_one_core"] is not None:
            summary[mode].update({k: statistics.median(r[k] for r in subset) for k in ["db_cpu_percent_one_core", "db_peak_rss_sum_bytes"]})
        if backup_results:
            summary[mode].update({k: statistics.median(r[k] for r in backup_results if r["mode"] == mode) for k in ["backup_seconds", "restore_seconds", "encrypted_bytes"]})
    report = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "status": "TESTED" if all(r["errors"] == 0 for r in results) else "FAILED",
              "boundary": "Sequential PostgreSQL business read/write, concurrency=1, no HTTP/TLS/auth overhead; runner CPU/RAM only",
              "dataset_records": len(ids), "seed": 2026, "read_write_mix": "80/20", "hardware": platform.platform(), "python": platform.python_version(),
              "target": "p95 < 100ms and zero unexpected errors, development goal only", "median": summary, "raw": results,
              "api_tls_benchmark": "NOT TESTED", "database_resource_boundary": "Native lab PostgreSQL process tree CPU; sum of working sets (shared memory may be counted repeatedly)",
              "synthetic_expansion": bool(args.env_file), "backup_restore": backup_results or "NOT TESTED"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "records": len(ids), "repeats": args.repeats, "median": summary}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Benchmark failed ({type(exc).__name__}); no plaintext data logged.", file=sys.stderr)
        sys.exit(1)
