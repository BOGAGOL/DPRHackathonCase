"""Read-only pgbench crosscheck; lookup corpus stays private, transaction logs contain no keys."""
from array import array
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
from uuid import uuid4

from psycopg import sql
import yaml

from .adapters.plaintext import SELECT, load_keys, PlaintextAdapter
from .common import ROOT, parameters, private_directory, file_hash, state, same_data, running_containers, utc_now, write_json
from .stats import percentile


def key_expression(values, offset=0):
    """Balanced CASE: no linear scan through 2048 keys per client transaction."""
    if not values or any(not re.fullmatch(r"[0-9]{14}", value) for value in values):
        raise ValueError("Expected fixed-width synthetic national identifiers")
    if len(values) == 1:
        return str(int(values[0]))
    middle = len(values) // 2
    return (f"CASE WHEN :key_index < {offset + middle} THEN " + key_expression(values[:middle], offset)
            + " ELSE " + key_expression(values[middle:], offset + middle) + " END")


def custom_script(profiles):
    values = [row["no_ktp"] for row in profiles]
    expression = key_expression(values)
    query = (SELECT + sql.SQL("WHERE no_ktp=lpad(:nik::text,14,'0');")).as_string()
    return f"\\set key_index random(0,{len(values)-1})\n\\set nik {expression}\n{query}\n"


def parse_output(output):
    patterns = {"requests": r"number of transactions actually processed:\s*(\d+)",
                "errors": r"number of failed transactions:\s*(\d+)",
                "throughput_rps": r"tps = ([0-9.]+)", "mean_ms": r"latency average = ([0-9.]+) ms"}
    matches = {key: re.search(pattern, output) for key, pattern in patterns.items()}
    if not all(matches.values()):
        raise ValueError("Incomplete pgbench aggregate output")
    return {key: (int(match[1]) if key in {"requests", "errors"} else float(match[1]))
            for key, match in matches.items()}


def transaction_metrics(paths, expected):
    latencies, errors = array("d"), 0
    for path in paths:
        with Path(path).open(encoding="utf-8") as handle:
            for line in handle:
                fields = line.split()
                if len(fields) != 6 or not 0 <= int(fields[0]) < 8 or int(fields[3]) != 0:
                    raise ValueError("Unexpected pgbench transaction log")
                if fields[2] in {"failed", "serialization", "deadlock"}:
                    errors += 1
                else:
                    latencies.append(float(fields[2]) / 1000)
    if len(latencies) != expected["requests"] or errors != expected["errors"] or not latencies:
        raise ValueError("pgbench raw log and aggregate counts disagree")
    return {"p50_ms": percentile(latencies, .5), "p95_ms": percentile(latencies, .95),
            "error_rate": errors / (len(latencies) + errors)}


def crosscheck(runs=3, duration=60, concurrency=8, session=None, power_guard=None):
    if (runs, duration, concurrency) != (3, 60, 8):
        raise ValueError("Crosscheck requires three 60-second runs and eight clients")
    output = ROOT / "evidence/benchmark/crosscheck_pgbench.json"
    raw = ROOT / "results/bench/crosscheck_pgbench"
    if session is not None:
        from .common import replacement_paths
        replacement_raw, replacement_evidence = replacement_paths(session)
        output = replacement_evidence / "crosscheck_pgbench.json"
        raw = replacement_raw / "crosscheck_pgbench"
    if output.exists() or raw.exists():
        raise ValueError("Existing crosscheck; refusing overwrite")
    if running_containers() != ["pg-dpr"]:
        raise ValueError("Expected only pg-dpr running")
    manifest = yaml.safe_load((ROOT / "benchmark/workloads.yaml").read_text(encoding="utf-8"))
    keys, corpus = load_keys(manifest, concurrency)
    old_env = json.loads((ROOT / "evidence/benchmark/baseline/env.json").read_text())
    if corpus["sha256"] != old_env["key_corpus"]["sha256"]:
        raise ValueError("100k corpus differs from original Python baseline")
    before = state()
    adapter = PlaintextAdapter(keys)
    with adapter.connect() as conn:
        for index in range(len(keys["profiles"])):
            adapter.execute(conn, "read_by_nik", index, 0)
    script = private_directory() / ("pgbench_nik_" + uuid4().hex + ".sql")
    with script.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(custom_script(keys["profiles"]))
    params = parameters()
    env = dict(os.environ, PGPASSWORD=params["password"])
    base = ["docker", "exec", "-i", "-e", "PGPASSWORD", "-e", "PGSSLMODE=disable", "pg-dpr", "pgbench",
            "-h", "127.0.0.1", "-p", "5432", "-U", "bench_user", "-n", "-c", "8", "-j", "8",
            "-M", "prepared", "--random-seed=42", "--exit-on-abort", "-f", "/dev/stdin"]
    report = {"status": "FAILED", "database": "baseline_100k", "started_at_utc": utc_now(),
              "runs": [], "parameters": {"runs": runs, "duration_s": duration, "concurrency": concurrency,
              "untimed_warmup_s": 10, "protocol": "prepared"}, "key_corpus": corpus,
              "lookup_pool_matches_original_python": True, "script_sha256": file_hash(script),
              "script_location": "DPR_PRIVATE_DIR/benchmark; fed over stdin, no key material in argv/repo",
              "transport": "pgbench in pg-dpr, TCP 127.0.0.1:5432, no TLS",
              "python_transport": "Windows host TCP 127.0.0.1:5433 through Docker Desktop",
              "comparability_limits": ["Same 2048-key pool and full 30-column SELECT; PRNG stream differs.",
                  "pgbench C client does not materialize Python objects or validate each row; Python runner does.",
                  "Container TCP and Windows Docker port path differ; delta cannot isolate Python overhead alone.",
                  "Balanced CASE lookup and lpad restore the fixed 14-digit key; these add small client/server work.",
                  "CPU percentages describe utilization, not proof excluding GIL/client bottlenecks."],
              "reference": "https://www.postgresql.org/docs/18/pgbench.html"}
    raw.mkdir(parents=True)
    phase = "warmup"
    try:
        for run in range(1, runs + 1):
            if power_guard:
                power_guard()
            if running_containers() != ["pg-dpr"]:
                raise ValueError("Container environment changed")
            prefix = "/tmp/dpr_pgbench_" + uuid4().hex + f"_r{run}"
            phase = "warmup"
            # Separate warmup process; connection/preparation startup of measured process remains documented.
            with script.open("rb") as handle:
                subprocess.run(base + ["-T", "10", "baseline_100k"], stdin=handle, env=env,
                               capture_output=True, check=True, timeout=40)
            phase = "measurement"
            if power_guard:
                power_guard()
            measurement_start = utc_now()
            with script.open("rb") as handle:
                result = subprocess.run(base + ["-T", "60", "-l", "--log-prefix=" + prefix, "baseline_100k"],
                                        stdin=handle, env=env, capture_output=True, check=True, timeout=100)
            row = {"run": run, "measurement_started_at_utc": measurement_start,
                   "measurement_completed_at_utc": utc_now(), **parse_output(result.stdout.decode("utf-8"))}
            phase = "raw log collection and validation"
            listing = subprocess.run(["docker", "exec", "pg-dpr", "find", "/tmp", "-maxdepth", "1", "-type", "f",
                                      "-name", prefix.split("/")[-1] + ".*"], capture_output=True, text=True, check=True)
            logs, local = listing.stdout.splitlines(), []
            if not logs or any(not re.fullmatch(re.escape(prefix) + r"\.[0-9]+(?:\.[0-9]+)?", name) for name in logs):
                raise ValueError("Unexpected temporary log paths")
            folder = raw / f"run_{run}"
            folder.mkdir()
            for name in logs:
                path = folder / name.split("/")[-1]
                subprocess.run(["docker", "cp", "pg-dpr:" + name, str(path)], capture_output=True, check=True)
                local.append(path)
            row.update(transaction_metrics(local, row))
            subprocess.run(["docker", "exec", "pg-dpr", "rm", "--", *logs], capture_output=True, check=True)
            row["container_temporary_logs_removed"] = True
            row["raw_sha256"] = {p.relative_to(raw).as_posix(): file_hash(p) for p in local}
            report["runs"].append(row)
            write_json(output, report)
            print(json.dumps({"phase": "pgbench_finished", "run": run, "throughput_rps": row["throughput_rps"],
                              "p95_ms": row["p95_ms"], "errors": row["errors"]}), flush=True)
            if power_guard:
                power_guard()
        report["data_and_sequence_unchanged"] = same_data(before, state())
        report["median_between_runs"] = {key: statistics.median(row[key] for row in report["runs"])
                                         for key in ("p50_ms", "p95_ms", "mean_ms", "throughput_rps", "error_rate")}
        python_summary = json.loads((ROOT / "evidence/benchmark/baseline/summary.json").read_text())
        reference = next(r for r in python_summary["median_between_runs"] if r["scenario"] == "read_by_nik")
        report["python_original_medians"] = {k: reference[k] for k in report["median_between_runs"]}
        report["ratios_pgbench_over_python"] = {k: report["median_between_runs"][k] / reference[k]
                                                  for k in ("p50_ms", "p95_ms", "mean_ms", "throughput_rps")}
        report["status"] = "PASSED" if report["data_and_sequence_unchanged"] and all(r["errors"] == 0 for r in report["runs"]) else "FAILED"
    except Exception as error:
        report["failure"] = {"phase": phase, "error_type": type(error).__name__,
                             "details": "Private script values and driver diagnostics withheld; no automatic retry"}
        raise
    finally:
        # Exact exclusively-created private script. Never print pgbench stderr: it can quote script values.
        script.unlink()
        report["private_temporary_script_removed"] = True
        report["completed_at_utc"] = utc_now()
        if session is not None:
            report.update(replacement_session=session, measurement_label="pengukuran pengganti AC")
        write_json(output, report)
    return report
