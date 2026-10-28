"""Closed-loop threaded duration runner. Raw request rows never contain lookup keys."""

from array import array
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import csv
import importlib.metadata
import json
import platform
import random
import statistics
import subprocess
import threading
import time

import psutil
import psycopg
import yaml

from datagen.database import source_rows, provenance
from datagen.model import checksum
from . import __version__
from .adapters.plaintext import PlaintextAdapter, load_keys
from .common import ROOT, RAW, EVIDENCE, parameters, state, same_data, running_containers, utc_now, write_json, write_csv, file_hash
from .collect_metrics import Collector
from .stats import summarize, medians


def operation_cycle(scenario, manifest, worker):
    rng = random.Random(manifest["seed"] + worker)
    cycle = [name for name, count in manifest["mixed_cycle"].items() for _ in range(count)]
    if len(cycle) != 100 or sum(manifest["mixed_cycle"][s] for s in manifest["scenarios"][:4]) != 70:
        raise ValueError("Mixed manifest must specify 70 read / 30 write operations")
    while True:
        if scenario == "mixed":
            rng.shuffle(cycle)
            yield from cycle
        else:
            yield scenario


def worker_run(adapter, conn, scenario, worker, manifest, barrier, measured_barrier, timing, path):
    warmup_errors = 0
    counts = Counter()
    latencies = array("d")
    successful = array("d")
    errors = 0
    rng = random.Random(manifest["seed"] + worker)
    warmup_ops = operation_cycle(scenario, manifest, worker)
    barrier.wait()
    while time.perf_counter() < timing["warmup_end"]:
        try:
            adapter.execute(conn, next(warmup_ops), rng.randrange(2**31), worker)
        except Exception:
            warmup_errors += 1
    # Reset operation/key stream at measurement start: same prefixes for every run/mode.
    ops = operation_cycle(scenario, manifest, worker)
    rng = random.Random(manifest["seed"] + worker)
    with path.open("x", encoding="utf-8", newline="", buffering=256 * 1024) as handle:
        writer = csv.writer(handle)
        writer.writerow(("timestamp_unix_utc", "scenario", "worker", "request_number", "operation", "latency_ms", "ok", "error_code"))
        measured_barrier.wait()
        index = 0
        while time.perf_counter() < timing["deadline"]:
            op = next(ops)
            key_index = rng.randrange(2**31)
            started = time.perf_counter()
            timestamp = timing["wall_start"] + started - timing["start"]
            ok = True
            try:
                adapter.execute(conn, op, key_index, worker)
            except Exception:
                errors += 1
                ok = False
            latency = (time.perf_counter() - started) * 1000
            latencies.append(latency)
            if ok:
                successful.append(latency)
            counts[op] += 1
            writer.writerow((f"{timestamp:.6f}", scenario, worker, index, op, f"{latency:.6f}", int(ok),
                             "" if ok else "operation_failed"))
            index += 1
    return {"latencies": latencies, "successful_latencies": successful, "errors": errors,
            "warmup_errors": warmup_errors, "counts": counts, "ended": time.perf_counter()}


def one_run(adapter, scenario, run, manifest, concurrency, duration, warmup, directory, db_monitor=None):
    directory.mkdir(parents=True, exist_ok=False)
    connections = [adapter.connect() for _ in range(concurrency)]
    timing = {"warmup_end": 0}
    collector = Collector(directory / "resources.csv")
    def start_measurement():
        if db_monitor is not None:
            timing["db_time_before"] = db_monitor.snapshot()
        timing.update(start=time.perf_counter(), wall_start=time.time())
        timing["deadline"] = timing["start"] + duration
        collector.start()
    barrier = threading.Barrier(concurrency + 1, timeout=30)
    measured_barrier = threading.Barrier(concurrency + 1, action=start_measurement, timeout=warmup + 30)
    try:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(worker_run, adapter, conn, scenario, i, manifest, barrier,
                measured_barrier, timing, directory / f"requests_worker_{i}.csv") for i, conn in enumerate(connections)]
            timing["warmup_end"] = time.perf_counter() + warmup
            barrier.wait()
            measured_barrier.wait()
            results = [future.result() for future in futures]
        elapsed = max(r["ended"] for r in results) - timing["start"]
        if db_monitor is not None:
            from .db_time import db_time_delta
            db_time = db_time_delta(timing["db_time_before"], db_monitor.snapshot(), sum(len(r["latencies"]) for r in results))
        else:
            db_time = None
        resource = collector.finish()
        all_latencies = array("d")
        success_latencies = array("d")
        counts = Counter()
        for result in results:
            all_latencies.extend(result["latencies"])
            success_latencies.extend(result["successful_latencies"])
            counts.update(result["counts"])
        summary = summarize(all_latencies, sum(r["errors"] for r in results), elapsed)
        summary.update(scenario=scenario, run=run, duration_s=duration, warmup_s=warmup,
                       started_at_utc=datetime.fromtimestamp(timing["wall_start"], timezone.utc).isoformat(),
                       completed_at_utc=utc_now(),
                       concurrency=concurrency, warmup_errors=sum(r["warmup_errors"] for r in results),
                       operations=dict(counts), resources=resource,
                       db_time=db_time,
                       successful_requests=summarize(success_latencies, 0, elapsed) if success_latencies else None)
        return summary
    finally:
        if collector.thread and collector.thread.is_alive():
            collector.finish()
        for conn in connections:
            conn.close()


def environment(manifest, config, before, corpus, database="baseline_100k"):
    with psycopg.connect(**parameters(database)) as conn:
        tls = conn.execute("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()").fetchone()[0]
        version = conn.execute("SHOW server_version").fetchone()[0]
        settings = dict(conn.execute("SELECT name,setting FROM pg_settings WHERE name=ANY(%s)",
            (["shared_buffers", "max_connections", "work_mem", "effective_cache_size", "max_parallel_workers_per_gather",
              "jit", "synchronous_commit", "fsync", "full_page_writes", "autovacuum", "log_statement",
              "log_min_duration_statement", "log_parameter_max_length_on_error"],)).fetchall())
        identity = conn.execute("SELECT current_user").fetchone()[0]
    if tls or identity != "bench_user":
        raise ValueError("Baseline must use bench_user without TLS")
    battery = psutil.sensors_battery()
    if battery and not battery.power_plugged:
        raise ValueError("Charger requirement not satisfied")
    power = subprocess.run(["powercfg", "/getactivescheme"], capture_output=True, text=True, check=False).stdout.strip()
    cpu = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).Name"],
                         capture_output=True, text=True, check=False).stdout.strip()
    inspect = json.loads(subprocess.run(["docker", "inspect", "pg-dpr"], capture_output=True, text=True, check=True).stdout)[0]
    docker_version = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"],
                                    capture_output=True, text=True, check=True).stdout.strip()
    return {"session_kind": "baseline_awal", "separate_from_paired_B_P_P_B": True, "level": "DB",
            "adapter": "plain", "endpoint": "127.0.0.1:5433", "database": database, "tls": False,
            "started_at_utc": utc_now(),
            "started_at_wib": datetime.now(timezone(timedelta(hours=7))).isoformat(),
            **provenance(), "benchmark_version": __version__,
            "parameters": config, "workload": manifest, "workload_sha256": file_hash(ROOT / "benchmark/workloads.yaml"),
            "dataset_before": before, "key_corpus": corpus, "database_user": identity,
            "os": platform.platform(), "cpu": cpu or platform.processor(), "logical_cpus": psutil.cpu_count(),
            "ram_bytes": psutil.virtual_memory().total, "python": platform.python_version(),
            "dependencies": {name: importlib.metadata.version(name) for name in ("psycopg", "psutil", "PyYAML")},
            "postgresql": version, "postgresql_settings": settings, "docker_version": docker_version,
            "container": {"name": "pg-dpr", "image": inspect["Config"]["Image"], "image_id": inspect["Image"],
                          "memory_limit_bytes": inspect["HostConfig"]["Memory"], "nano_cpus": inspect["HostConfig"]["NanoCpus"]},
            "running_containers": running_containers(), "power_plugged_verified": battery.power_plugged if battery else None,
            "active_power_scheme": power,
            "user_reported_conditions": {"charger": True, "power_mode": "Best performance", "no_heavy_apps": "not independently verified this session",
                                         "other_containers_stopped": True},
            "team_decision": {"all_databases": "pg-dpr:5433 (baseline_100k, baseline_1m, protected datasets)",
                              "openbao": "infra/compose.yaml Modul A", "excluded": ["optional PostgreSQL 5434", "root Compose PostgreSQL 17"]},
            "targets": {"DB_P01_P03": "BELUM DIUJI: protected adapter not measured", "API_P01_P03": "BELUM DIUJI"}}


def baseline_run(runs=3, duration=60, concurrency=8, warmup=10, scenario="all", database="baseline_100k"):
    if runs < 3 or min(duration, concurrency, warmup) <= 0:
        raise ValueError("At least three runs and positive timings/concurrency required")
    from .common import BASELINE_ROWS, session_paths, require_disk_space
    raw, evidence = (RAW, EVIDENCE) if database == "baseline_100k" else session_paths(database)
    disk_free = require_disk_space() if database == "baseline_1m" else None
    if (raw / "env.json").exists():
        raise ValueError("Existing baseline session; refusing overwrite")
    if running_containers() != ["pg-dpr"]:
        raise ValueError("Expected only pg-dpr running")
    manifest = yaml.safe_load((ROOT / "benchmark/workloads.yaml").read_text(encoding="utf-8"))
    scenarios = manifest["scenarios"] if scenario == "all" else [scenario]
    if any(s not in manifest["scenarios"] for s in scenarios):
        raise ValueError("Unknown scenario")
    expected = json.loads((ROOT / "evidence/datasets" / (database + ".json")).read_text(encoding="utf-8"))
    before = state(database)
    if before["rows"] != BASELINE_ROWS[database] or before["checksum_sha256"] != expected["baseline_checksum_sha256"]:
        raise ValueError("Baseline differs from validated generation")
    source_before = checksum(source_rows())
    keys, corpus = load_keys(manifest, concurrency, database)
    adapter = PlaintextAdapter(keys, database)
    # Untimed functional probe for every worker and operation, plus rollback/sequence proof.
    for worker in range(concurrency):
        with adapter.connect() as conn:
            for op in manifest["scenarios"][:-1]:
                adapter.execute(conn, op, worker, worker)
    if not same_data(before, state(database)):
        raise ValueError("Functional preflight altered dataset or sequence")
    config = dict(runs=runs, duration_s=duration, concurrency=concurrency, warmup_s=warmup, scenario=scenario)
    meta = environment(manifest, config, before, corpus, database)
    meta["disk_preflight_free_bytes"] = disk_free
    raw.mkdir(parents=True, exist_ok=True)
    write_json(raw / "env.json", meta)
    write_json(evidence / "env.json", meta)
    summaries = []
    for name in scenarios:
        for run in range(1, runs + 1):
            if running_containers() != ["pg-dpr"]:
                raise ValueError("Container environment changed during session")
            # Uniform maintenance on baseline only, outside measured/warmup windows.
            if database == "baseline_1m":
                require_disk_space()
            with psycopg.connect(**parameters(database, admin=True), autocommit=True) as admin:
                admin.execute("VACUUM (ANALYZE) public.anggota")
            print(json.dumps({"phase": "starting", "scenario": name, "run": run, "at_utc": utc_now()}), flush=True)
            result = one_run(adapter, name, run, manifest, concurrency, duration, warmup, raw / name / f"run_{run}")
            after = state(database)
            result["dataset_after"] = after
            result["data_and_sequence_unchanged"] = same_data(before, after)
            result["telemetry_complete"] = result["resources"]["samples"] > 0 and result["resources"]["failed_samples"] == 0
            result["valid"] = result["data_and_sequence_unchanged"] and result["resources"]["samples"] > result["resources"]["failed_samples"]
            summaries.append(result)
            write_json(raw / "run_summaries.json", summaries)
            write_json(evidence / "run_summaries.json", summaries)
            print(json.dumps({"phase": "finished", "scenario": name, "run": run,
                "p50_ms": result["p50_ms"], "p95_ms": result["p95_ms"], "throughput_rps": result["throughput_rps"],
                "errors": result["errors"], "valid": result["valid"]}), flush=True)
            if not result["valid"]:
                raise ValueError("Run integrity or resource verification failed; raw retained")
    source_after = checksum(source_rows())
    combined = []
    for name in scenarios:
        group = [r for r in summaries if r["scenario"] == name]
        metrics = {"scenario": name, "runs": runs, **medians(group),
                   "requests_total": sum(r["requests"] for r in group), "errors_total": sum(r["errors"] for r in group)}
        for field in ("db_cpu_percent_one_core_median", "db_ram_bytes_peak", "client_cpu_percent_one_core_median", "client_cpu_percent_one_core_peak", "client_ram_bytes_peak"):
            values = [r["resources"].get(field) for r in group if r["resources"].get(field) is not None]
            metrics[field + "_between_runs"] = statistics.median(values) if values else None
        combined.append(metrics)
    status = "PASSED" if source_before == source_after and all(r["errors"] == 0 and r["warmup_errors"] == 0 and r["telemetry_complete"] for r in summaries) else "FAILED"
    result = {"status": status, "session_kind": "baseline_awal", "level": "DB", "adapter": "plain",
              "median_between_runs": combined, "source_database_unchanged": source_before == source_after,
              "source_checksum_sha256": source_after, "completed_at_utc": utc_now(),
              "database": database, "raw_requests_location": raw.relative_to(ROOT).as_posix() + "/<scenario>/run_<n>/requests_worker_<n>.csv",
              "target_comparison": "BELUM DIUJI: no protected or API measurements in initial baseline"}
    for directory in (raw, evidence):
        write_json(directory / "summary.json", result)
        write_csv(directory / "summary.csv", combined)
        write_csv(directory / "run_summaries.csv", [{k: v for k, v in r.items() if not isinstance(v, dict)} for r in summaries])
    return result
