"""Offline power-incident audit. Never connect to DB, Docker, or execute a workload."""
import csv
from datetime import datetime, timedelta, timezone
import gzip
import json
from pathlib import Path
import statistics
import subprocess

from .common import ROOT, file_hash, utc_now, write_csv, write_json

WIB = timezone(timedelta(hours=7))
REPORTED_START = "2026-10-27T19:00:00+07:00"
REPORTED_END = "2026-10-27T19:21:00+07:00"


def timestamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("Audit timestamps must include timezone")
    return result


def overlap(start, end, interval):
    return max(0., (min(end, timestamp(interval["end_wib"])) - max(start, timestamp(interval["start_wib"]))).total_seconds())


def battery_intervals(events):
    intervals, pending = [], None
    for event in sorted(events, key=lambda row: timestamp(row["time_utc"])):
        if event["event_id"] != 105:
            continue
        online = event["data"].get("AcOnline", "").lower()
        if online not in {"true", "false"}:
            raise ValueError("Power-source event missing explicit AC state")
        if online == "false" and pending is None:
            pending = event
        elif online == "true" and pending:
            interval = {"start_wib": pending["time_wib"], "end_wib": event["time_wib"],
                        "unplug_record_id": pending["record_id"], "replug_record_id": event["record_id"]}
            interval["duration_s"] = (timestamp(interval["end_wib"]) - timestamp(interval["start_wib"])).total_seconds()
            intervals.append(interval)
            pending = None
    return intervals


def resource_rows(path):
    with (gzip.open(path, "rt", encoding="utf-8") if path.suffix == ".gz" else path.open(encoding="utf-8")) as handle:
        return list(csv.DictReader(handle))


def resource_summary(rows):
    good = [row for row in rows if row["ok"].lower() == "true"]
    output = {"samples": len(rows), "failed": len(rows) - len(good)}
    for field in ("db_cpu_percent_one_core", "client_cpu_percent_one_core", "db_ram_bytes", "client_ram_bytes"):
        values = [float(row[field]) for row in good]
        output[field + "_median"] = statistics.median(values) if values else None
        output[field + "_peak"] = max(values) if values else None
    return output


def analyze_runs(runs, resources, incident):
    output = []
    reported = {"start_wib": REPORTED_START, "end_wib": REPORTED_END}
    for row in runs:
        start = timestamp(row["started_at_utc"]).astimezone(WIB)
        end = start + timedelta(seconds=row["elapsed_s"])
        others = [other for other in runs if other["scenario"] == row["scenario"] and other["run"] != row["run"]]
        comparisons = {}
        for field in ("p50_ms", "p95_ms", "throughput_rps"):
            peer = statistics.median(other[field] for other in others)
            comparisons[field] = {"value": row[field], "other_two_runs_median": peer,
                                  "difference_percent": 100 * (row[field] / peer - 1) if peer else None}
        samples = resources[(row["scenario"], row["run"])]
        during_reported = [s for s in samples if timestamp(REPORTED_START) <= timestamp(s["timestamp_utc"]) < timestamp(REPORTED_END)]
        during_incident = [s for s in samples if timestamp(incident["start_wib"]) <= timestamp(s["timestamp_utc"]) < timestamp(incident["end_wib"])]
        output.append({"scenario": row["scenario"], "run": row["run"], "started_at_wib": start.isoformat(),
                       "ended_at_wib": end.isoformat(), "elapsed_s": row["elapsed_s"],
                       "end_method": "started_at_utc + measured elapsed_s (includes worker drain); completed_at_utc is later bookkeeping",
                       "completed_at_wib": timestamp(row["completed_at_utc"]).astimezone(WIB).isoformat(),
                       "reported_window_overlap_s": overlap(start, end, reported),
                       "confirmed_battery_overlap_s": overlap(start, end, incident),
                       "warmup_estimated_overlap_s": overlap(start - timedelta(seconds=row["warmup_s"]), start, incident),
                       "errors": row["errors"], "comparisons": comparisons,
                       "resources": resource_summary(samples), "reported_window_resources": resource_summary(during_reported),
                       "confirmed_incident_resource_samples": len(during_incident),
                       "first_resource_wib": timestamp(samples[0]["timestamp_utc"]).astimezone(WIB).isoformat() if samples else None,
                       "last_resource_wib": timestamp(samples[-1]["timestamp_utc"]).astimezone(WIB).isoformat() if samples else None})
    return output


def pgbench_bounds(folder):
    """Read only first/last transaction of each thread log, not millions of rows."""
    times = []
    for path in sorted(folder.iterdir()):
        if not path.is_file():
            continue
        with path.open("rb") as handle:
            first = handle.readline()
            handle.seek(max(0, path.stat().st_size - 4096))
            last = handle.read().splitlines()[-1]
        for line in (first, last):
            fields = line.split()
            if len(fields) != 6:
                raise ValueError("Unexpected pgbench log format")
            times.append(datetime.fromtimestamp(int(fields[4]) + int(fields[5]) / 1e6, WIB))
    if not times:
        raise ValueError("Missing pgbench raw logs")
    return min(times), max(times)


def secondary_phases(backup, pgbench, raw, incident):
    backups = []
    for run in backup["runs"]:
        start = timestamp(run["started_at_utc"]).astimezone(WIB)
        backup_end = start + timedelta(seconds=run["backup_s"])
        restore_end = backup_end + timedelta(seconds=run["restore_s"])
        backups.append({"run": run["run"], "started_at_wib": start.isoformat(),
                        "backup_end_approx_wib": backup_end.isoformat(), "restore_end_approx_wib": restore_end.isoformat(),
                        "backup_s": run["backup_s"], "restore_s": run["restore_s"],
                        "backup_battery_overlap_approx_s": overlap(start, backup_end, incident),
                        "restore_battery_overlap_approx_s": overlap(backup_end, restore_end, incident)})
    checks = []
    for run in pgbench["runs"]:
        first, last = pgbench_bounds(raw / f"run_{run['run']}")
        checks.append({"run": run["run"], "first_transaction_complete_wib": first.isoformat(),
                       "last_transaction_complete_wib": last.isoformat(),
                       "observed_transaction_span_battery_overlap_s": overlap(first, last, incident),
                       **{key: run[key] for key in ("p50_ms", "p95_ms", "throughput_rps", "errors")}})
    return {"backup_restore": backups,
            "backup_time_precision": "Approximate stage boundaries from run start + perf_counter durations; phase transition overhead not separately timestamped",
            "pgbench_crosscheck": checks, "pgbench_time_precision": "First/last transaction completions across thread logs, not process start/finish",
            "cpu_resource_during_incident": "UNAVAILABLE: official collector stops after last workload run at 19:14:30 WIB; backup/pgbench have no equivalent resource CSV"}


def run(root=ROOT):
    directory = root / "evidence/benchmark/baseline_1m"
    events = json.loads((directory / "power_events.json").read_text(encoding="utf-8"))
    incidents = [i for i in battery_intervals(events["events"]) if overlap(timestamp(REPORTED_START), timestamp(REPORTED_END), i)]
    if len(incidents) != 1:
        raise ValueError("Expected one confirmed battery interval intersecting reported window")
    incident = incidents[0]
    original_paths = [directory / name for name in ("env.json", "run_summaries.json", "summary.json", "backup_restore.json")]
    original_paths += [root / "evidence/benchmark/crosscheck_pgbench.json", root / "evidence/benchmark/session_1m_crosscheck.json"]
    inputs = {p.relative_to(root).as_posix(): file_hash(p) for p in original_paths}
    runs = json.loads((directory / "run_summaries.json").read_text(encoding="utf-8"))
    resources = {}
    for row in runs:
        path = root / "results/bench/before_1m" / row["scenario"] / f"run_{row['run']}" / "resources.csv.gz"
        resources[(row["scenario"], row["run"])] = resource_rows(path)
    analyzed = analyze_runs(runs, resources, incident)
    backup = json.loads((directory / "backup_restore.json").read_text(encoding="utf-8"))
    pgbench = json.loads((root / "evidence/benchmark/crosscheck_pgbench.json").read_text(encoding="utf-8"))
    secondary = secondary_phases(backup, pgbench, root / "results/bench/crosscheck_pgbench", incident)
    report = {"status": "ANALYZED_NO_RERUN", "timestamp_utc": utc_now(), "dataset": "baseline_1m",
              "user_report": {"possible_window_start_wib": REPORTED_START, "possible_window_end_wib": REPORTED_END,
                              "approximate_duration_s": 60, "interpretation": "19:00-19:21 WIB on benchmark date; approximate recollection, not a 21-minute outage"},
              "confirmed_interval": incident, "windows_events_file": "evidence/benchmark/baseline_1m/power_events.json",
              "inputs_at_analysis_sha256": inputs,
              "source_git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
              "workload_runs": analyzed, "secondary_phases": secondary,
              "conclusion": {"workload_runs_confirmed_overlap": sum(r["confirmed_battery_overlap_s"] > 0 for r in analyzed),
                             "workload_runs_in_reported_uncertain_window": sum(r["reported_window_overlap_s"] > 0 for r in analyzed),
                             "last_workload_end_wib": max(r["ended_at_wib"] for r in analyzed),
                             "battery_started_after_last_workload_end_s": (timestamp(incident["start_wib"]) - max(timestamp(r["ended_at_wib"]) for r in analyzed)).total_seconds(),
                             "statement": ("No workload measurement/warmup overlaps logged power loss. " if not any(r["confirmed_battery_overlap_s"] or r["warmup_estimated_overlap_s"] for r in analyzed)
                                           else "Some workload measurement/warmup intervals overlap logged power loss. ") +
                                          "Review per-run secondary phase overlaps; overlap alone does not establish quantified causal slowdown."},
              "limitations": ["CPU/RAM samples are sparse and not battery-state, clock-frequency, thermal or power-plan telemetry.",
                              "No CPU/resource samples exist during confirmed incident; do not substitute zeros or earlier samples.",
                              "Kernel events 506/507 at 19:18:06/19:18:52 describe a Modern Standby session; SleepEntered=false and SleepDurationInUs=0, so do not infer a 46-second CPU suspension.",
                              "Original timing/error/integrity metrics retained; no run dropped, median changed, workload or restore repeated."]}
    write_json(directory / "power_incident.json", report)
    timeline = []
    for row in analyzed:
        timeline.append({"scenario": row["scenario"], "run": row["run"], "started_at_wib": row["started_at_wib"],
                         "ended_at_wib": row["ended_at_wib"], "reported_window_overlap_s": row["reported_window_overlap_s"],
                         "confirmed_battery_overlap_s": row["confirmed_battery_overlap_s"],
                         **{key: row["comparisons"][key]["value"] for key in ("p50_ms", "p95_ms", "throughput_rps")},
                         **{key + "_vs_other_two_pct": row["comparisons"][key]["difference_percent"] for key in ("p50_ms", "p95_ms", "throughput_rps")},
                         **row["resources"]})
    write_csv(directory / "power_run_timeline.csv", timeline)
    return report


def annotate_metadata(report, root=ROOT):
    """Append qualifications; never alter timings, errors, validity or medians."""
    directory = root / "evidence/benchmark/baseline_1m"
    reference = "evidence/benchmark/baseline_1m/power_incident.json"
    base = {"recorded_at_utc": report["timestamp_utc"], "incident_file": reference,
            "confirmed_battery_interval": report["confirmed_interval"],
            "verification_scope": "Historical charger=true was a preflight observation/user report, not continuous AC telemetry",
            "no_rerun_no_metrics_removed": True}
    for filename in ("env.json", "summary.json"):
        path = directory / filename
        document = json.loads(path.read_text(encoding="utf-8"))
        count = report["conclusion"]["workload_runs_confirmed_overlap"]
        document["post_run_power_audit"] = {**base, "workload_runs_overlapping_confirmed_incident": count,
                                            "workload_interpretation": "No measured run overlaps logged AC interruption" if count == 0 else "Measurement overlap present; see incident report"}
        write_json(path, document)
    path = directory / "run_summaries.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    for row in document:
        analysis = next(r for r in report["workload_runs"] if (r["scenario"], r["run"]) == (row["scenario"], row["run"]))
        row["post_run_power_audit"] = {"incident_file": reference,
                                       "confirmed_battery_overlap_s": analysis["confirmed_battery_overlap_s"],
                                       "reported_uncertain_window_overlap_s": analysis["reported_window_overlap_s"]}
    write_json(path, document)
    path = directory / "backup_restore.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["post_run_power_audit"] = {**base, "performance_qualification": "ENVIRONMENT_DEVIATION: restore run 2 tail and backup/restore run 3 overlap battery; integrity PASSED retained"}
    for row in document["runs"]:
        analysis = next(r for r in report["secondary_phases"]["backup_restore"] if r["run"] == row["run"])
        row["post_run_power_audit"] = {"incident_file": reference,
                                       **{key: analysis[key] for key in ("backup_battery_overlap_approx_s", "restore_battery_overlap_approx_s")}}
    write_json(path, document)
    path = root / "evidence/benchmark/crosscheck_pgbench.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["post_run_power_audit"] = {**base, "performance_qualification": "ENVIRONMENT_DEVIATION: all three pgbench runs on battery vs original Python baseline on AC; ratio is descriptive, not a controlled Python-overhead estimate",
                                        "transaction_time_windows": report["secondary_phases"]["pgbench_crosscheck"]}
    caveat = "Retrospective Kernel-Power audit: all pgbench runs on battery, while original Python baseline ran on AC; power conditions not matched."
    if caveat not in document["comparability_limits"]:
        document["comparability_limits"].append(caveat)
    write_json(path, document)
    path = root / "evidence/benchmark/session_1m_crosscheck.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["post_run_power_audit"] = {**base, "qualification": "Workload 1M has no recorded overlap; later backup/restore and pgbench were not continuously on AC. PASSED denotes original integrity/execution checks."}
    write_json(path, document)


if __name__ == "__main__":
    report = run()
    annotate_metadata(report)
    print(json.dumps(report["conclusion"], indent=2))
