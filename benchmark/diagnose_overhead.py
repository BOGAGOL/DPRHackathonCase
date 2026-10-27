"""Bounded read-only diagnostics, deliberately separate from official baselines."""
from concurrent.futures import ThreadPoolExecutor
import csv
import json
from pathlib import Path
import random
import subprocess
import threading
import time

import psutil
import psycopg
import yaml

from .adapters.plaintext import PlaintextAdapter, SELECT, load_keys
from .common import ROOT, parameters, private_directory, utc_now, write_json
from .stats import percentile
from psycopg import sql


def distribution(values):
    return {"samples": len(values), "mean_ms": sum(values) / len(values),
            "p50_ms": percentile(values, .5), "p95_ms": percentile(values, .95)}


class TimedConnection:
    """Time driver calls without changing the existing adapter implementation."""
    def __init__(self, connection):
        self.connection = connection
        self.execute_ms = self.fetch_ms = 0.
        self.cursor = None

    def execute(self, *args, **kwargs):
        started = time.perf_counter()
        self.cursor = self.connection.execute(*args, **kwargs)
        self.execute_ms = (time.perf_counter() - started) * 1000
        return self

    def fetchall(self):
        started = time.perf_counter()
        result = self.cursor.fetchall()
        self.fetch_ms = (time.perf_counter() - started) * 1000
        return result


def diagnostic_worker(adapter, connection, worker, count, barrier, path):
    connection.execute("SET default_transaction_read_only=on")
    pid = connection.info.backend_pid
    # Preparation and socket establishment are outside the diagnostic sample.
    for index in range(32):
        adapter.execute(connection, "read_by_nik", index, worker)
    proxy = TimedConnection(connection)
    rng = random.Random(42 + worker)
    samples = []
    with path.open("x", encoding="utf-8", newline="", buffering=256 * 1024) as handle:
        writer = csv.writer(handle)
        writer.writerow(("worker", "request", "execute_ms", "fetch_ms", "adapter_other_ms", "latency_ms", "bookkeeping_ms"))
        barrier.wait()
        cpu_started = time.thread_time()
        started = time.perf_counter()
        for index in range(count):
            loop = time.perf_counter()
            key = rng.randrange(2**31)
            begin = time.perf_counter()
            adapter.execute(proxy, "read_by_nik", key, worker)
            latency = (time.perf_counter() - begin) * 1000
            other = latency - proxy.execute_ms - proxy.fetch_ms
            # Formatting + buffered CSV are outside latency, as in worker_run.
            writer.writerow((worker, index, proxy.execute_ms, proxy.fetch_ms, other, latency, ""))
            bookkeeping = (time.perf_counter() - loop) * 1000 - latency
            samples.append((proxy.execute_ms, proxy.fetch_ms, other, latency, bookkeeping))
        elapsed = time.perf_counter() - started
        cpu = time.thread_time() - cpu_started
    return {"samples": samples, "elapsed_s": elapsed, "thread_cpu_s": cpu,
            "persistent_backend_pid_unchanged": connection.info.backend_pid == pid,
            "prepared_statement_count": connection.execute("SELECT count(*) FROM pg_prepared_statements").fetchone()[0]}


def measure(adapter, concurrency, requests, directory):
    if requests % concurrency or requests < concurrency:
        raise ValueError("Request count must be divisible by concurrency")
    directory.mkdir(parents=True, exist_ok=False)
    connections = []
    process = psutil.Process()
    try:
        connections = [adapter.connect() for _ in range(concurrency)]
        barrier = threading.Barrier(concurrency)
        cpu_before = process.cpu_times()
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [pool.submit(diagnostic_worker, adapter, conn, i, requests // concurrency, barrier,
                                   directory / f"worker_{i}.csv") for i, conn in enumerate(connections)]
            workers = [future.result() for future in futures]
        cpu_after = process.cpu_times()
        elapsed = time.perf_counter() - started
        samples = [sample for worker in workers for sample in worker["samples"]]
        fields = ("psycopg_execute", "psycopg_fetchall", "runner_adapter_other", "request_latency", "runner_bookkeeping_csv")
        return {"concurrency": concurrency, "requests": len(samples), "errors": 0,
                "connection_count": len(connections), "connections_opened_per_request": False,
                "persistent_backends_verified": all(w["persistent_backend_pid_unchanged"] for w in workers),
                "prepared_statement_counts": [w["prepared_statement_count"] for w in workers],
                "components": {name: distribution([sample[i] for sample in samples]) for i, name in enumerate(fields)},
                "measured_throughput_rps": requests / max(w["elapsed_s"] for w in workers),
                "thread_cpu_s": sum(w["thread_cpu_s"] for w in workers),
                "process_cpu_s_including_preparation": cpu_after.user + cpu_after.system - cpu_before.user - cpu_before.system,
                "wall_s_including_preparation": elapsed,
                "gil_conclusion": "No lock profiler used; low overall CPU cannot rule out single-thread/GIL scheduling effects."}
    finally:
        for connection in connections:
            connection.close()


def sanitize_explain(document):
    """Never export plans: Index Cond can embed the private lookup parameter."""
    root = document[0]
    plan = root["Plan"]
    return {"planning_ms": root.get("Planning Time"), "execution_ms": root["Execution Time"],
            "node_type": plan["Node Type"], "index_name": plan.get("Index Name"),
            **{key: plan.get(key, 0) for key in
               ("Shared Hit Blocks", "Shared Read Blocks", "Shared Dirtied Blocks", "Shared Written Blocks", "Actual Rows")}}


def cache_snapshot(database):
    with psycopg.connect(**parameters(database), autocommit=True) as conn:
        conn.execute("SET default_transaction_read_only=on")
        # Use pg_settings units instead of assuming SHOW uses MB.
        shared_bytes = conn.execute("SELECT setting::bigint * pg_size_bytes(unit) FROM pg_settings WHERE name='shared_buffers'").fetchone()[0]
        indexes = conn.execute(
            "SELECT indexrelname,pg_relation_size(indexrelid),idx_blks_read,idx_blks_hit "
            "FROM pg_statio_user_indexes WHERE relid='public.anggota'::regclass ORDER BY indexrelname").fetchall()
        table = conn.execute("SELECT heap_blks_read,heap_blks_hit FROM pg_statio_user_tables WHERE relid='public.anggota'::regclass").fetchone()
        db = conn.execute("SELECT blks_read,blks_hit,stats_reset FROM pg_stat_database WHERE datname=current_database()").fetchone()
        preload_row = conn.execute("SELECT setting FROM pg_settings WHERE name='shared_preload_libraries'").fetchone()
        preload = preload_row[0] if preload_row else None
        extension = conn.execute("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname='pg_stat_statements')").fetchone()[0]
        return {"database": database, "at_utc": utc_now(), "shared_buffers_bytes": shared_bytes,
                "table_heap_bytes": conn.execute("SELECT pg_relation_size('public.anggota')").fetchone()[0],
                "total_index_bytes": sum(r[1] for r in indexes),
                "indexes": [{"name": r[0], "bytes": r[1], "blocks_read": r[2], "blocks_hit": r[3],
                             "hit_ratio": r[3] / (r[2] + r[3]) if r[2] + r[3] else None} for r in indexes],
                "heap": {"blocks_read": table[0], "blocks_hit": table[1], "hit_ratio": table[1] / sum(table) if sum(table) else None},
                "database_cache_hit_ratio": db[1] / (db[0] + db[1]) if db[0] + db[1] else None,
                "stats_reset": str(db[2]), "pg_stat_statements_installed": extension,
                "pg_stat_statements_preloaded": "pg_stat_statements" in preload if preload is not None else None}


def explain_samples(adapter, count=32):
    output = []
    with adapter.connect() as conn:
        conn.execute("SET default_transaction_read_only=on")
        query = sql.SQL("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ") + SELECT + sql.SQL("WHERE no_ktp=%s")
        for row in adapter.keys["profiles"][:count]:
            output.append(sanitize_explain(conn.execute(query, (row["no_ktp"],)).fetchone()[0]))
    return {"requests": len(output), "instrumentation": "EXPLAIN ANALYZE TIMING ON; separate sample, not a per-request subtraction",
            "execution": distribution([r["execution_ms"] for r in output]),
            "planning": distribution([r["planning_ms"] for r in output]), "sanitized_samples": output}


def run(requests=2000):
    timestamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    raw = ROOT / "results/bench/diagnostics" / timestamp
    manifest = yaml.safe_load((ROOT / "benchmark/workloads.yaml").read_text())
    report = {"kind": "bounded_diagnostic_not_official_benchmark", "started_at_utc": utc_now(),
              "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              "instrumentation_worktree": True, "database": "baseline_100k", "tls": False,
              "scope": "2000 requests TOTAL per concurrency (not per worker), plus 32 warmup requests/worker and 32 EXPLAINs/database",
              "audit": {"connections": "one per worker, opened before measured loop", "csv": "256 KiB buffered; after latency; no per-request flush/fsync",
                        "validation": "one 30-field tuple comparison; expected tuple constructed per request", "gil": "threaded psycopg; no explicit shared lock in request path"},
              "measurements": []}
    for database in ("baseline_100k", "baseline_1m"):
        if not (private_directory() / (database + "_keys_v1.json")).exists():
            raise ValueError("Existing private key corpus required; refusing generation")
        keys, corpus = load_keys(manifest, 8, database)
        adapter = PlaintextAdapter(keys, database)
        before = cache_snapshot(database)
        measurements = [measure(adapter, c, requests, raw / f"c{c}") for c in (1, 8)] if database == "baseline_100k" else []
        explain = explain_samples(adapter)
        report[database] = {"corpus": corpus, "cache_before": before, "cache_after": cache_snapshot(database), "server_explain": explain}
        report["measurements"].extend(measurements)
        write_json(ROOT / "evidence/benchmark/runner_overhead.json", report)
    report.update(completed_at_utc=utc_now(), raw_location=raw.relative_to(ROOT).as_posix(),
                  official_baselines_changed=False, implementation_defect_found=False,
                  limitations=["Driver execute includes socket wait, libpq and client/server scheduling, not just Python CPU.",
                               "Instrumentation perturbs timings; components add for each request, percentiles do not add.",
                               "Current cumulative cache counters and 32 EXPLAINs cannot reconstruct historical 1M p95 causality.",
                               "pgbench ran inside container; Python uses Windows Docker forwarded port. Transport and result handling differ."],
                  proposal="Report pg_stat_statements interval delta total_exec_time/calls as db_time beside end-to-end latency in future paired before/after; enable consistently before both modes, no global resets; account for other sessions and planning separately.")
    write_json(ROOT / "evidence/benchmark/runner_overhead.json", report)
    return report


if __name__ == "__main__":
    try:
        result = run()
        print(json.dumps({"status": "PASSED", "requests": [r["requests"] for r in result["measurements"]],
                          "evidence": "evidence/benchmark/runner_overhead.json"}))
    except Exception:
        raise SystemExit("Diagnostic failed; details withheld to protect parameters/credentials") from None
