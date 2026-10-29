"""One authorized AC replacement: only 1M backup/restore and 100k pgbench."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import time

from datagen.database import provenance
from .ac_monitor import ACMonitor
from .backup_restore import backup_restore
from .common import ROOT, file_hash, replacement_paths, require_disk_space, running_containers, utc_now, write_csv, write_json
from .pgbench_crosscheck import crosscheck

OLD_FILES = ("baseline_1m/backup_restore.json", "baseline_1m/backup_restore/runs.csv",
             "crosscheck_pgbench.json", "baseline_1m/env.json", "baseline_1m/summary.json",
             "session_1m_crosscheck.json", "baseline_1m/power_incident.json", "baseline_1m/power_events.json")
PROTECTED_FILES = ("evidence/benchmark/baseline_1m/run_summaries.json", "evidence/benchmark/baseline_1m/summary.csv",
                   "evidence/benchmark/baseline_1m/raw_validation.json", "evidence/benchmark/baseline/summary.json",
                   "scanner/ground_truth_eval.csv", "docs/ground_truth_methodology.md", "docs/targets.md")


def archive_originals(session, root=ROOT):
    history = root / "evidence/benchmark/history" / ("battery_affected_" + session)
    history.mkdir(parents=True, exist_ok=False)
    copied = {}
    for name in OLD_FILES:
        source = root / "evidence/benchmark" / name
        target = history / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if file_hash(source) != file_hash(target):
            raise ValueError("Historical evidence copy checksum mismatch")
        copied[name] = file_hash(target)
    manifest = {"label": "terdampak baterai", "superseded_by_session": session, "archived_at_utc": utc_now(),
                "label_scope": "Original session bundle; backup R1 did not overlap, restore R2 tail and R3 did; all original pgbench runs were on battery",
                "files_byte_identical_to_pre_replacement": copied,
                "raw_retained_in_place": ["results/bench/before_1m/backup_restore/", "results/bench/crosscheck_pgbench/"],
                "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()}
    write_json(history / "manifest.json", manifest)
    return history


def promote(session, backup, pgbench, power, history, root=ROOT):
    if not power["qualified"] or backup["status"] != "PASSED" or pgbench["status"] != "PASSED":
        raise ValueError("Incomplete or power-unqualified replacement must not become active")
    raw, evidence = replacement_paths(session)
    prefix = evidence.relative_to(root).as_posix()
    history_ref = history.relative_to(root).as_posix()
    for report, old_name in ((backup, "baseline_1m/backup_restore.json"), (pgbench, "crosscheck_pgbench.json")):
        report.update(measurement_label="pengukuran pengganti AC", replacement_session=session,
                      ac_verified_entire_session=True, power_verification_file=prefix + "/power_verification.json",
                      original_battery_affected_evidence=history_ref + "/" + old_name,
                      original_measurement_label="terdampak baterai")
    backup["raw_location"] = (raw / "baseline_1m/backup_restore").relative_to(root).as_posix()
    pgbench["raw_location"] = (raw / "crosscheck_pgbench").relative_to(root).as_posix()
    for path in (evidence / "baseline_1m/backup_restore.json", root / "evidence/benchmark/baseline_1m/backup_restore.json", raw / "baseline_1m/backup_restore.json"):
        write_json(path, backup)
    for path in (evidence / "baseline_1m/backup_restore/runs.csv", root / "evidence/benchmark/baseline_1m/backup_restore/runs.csv"):
        write_csv(path, backup["runs"])
    for path in (evidence / "crosscheck_pgbench.json", root / "evidence/benchmark/crosscheck_pgbench.json"):
        write_json(path, pgbench)
    write_csv(evidence / "pgbench_runs.csv", [{k: row[k] for k in ("run", "p50_ms", "p95_ms", "throughput_rps", "errors")} for row in pgbench["runs"]])
    active = {"replacement_session": session, "power_verification_file": prefix + "/power_verification.json",
              "workload_21_runs_repeated": False,
              "workload_1m": {"file": "evidence/benchmark/baseline_1m/summary.json", "measurement": "original unaffected 21 runs"},
              "backup_restore_1m": {"file": "evidence/benchmark/baseline_1m/backup_restore.json", "medians": backup["medians"]},
              "pgbench_crosscheck_100k": {"file": "evidence/benchmark/crosscheck_pgbench.json", "medians": pgbench["median_between_runs"]},
              "historical_measurements": {"label": "terdampak baterai", "manifest": history_ref + "/manifest.json"}}
    write_json(root / "evidence/benchmark/active_measurements.json", active)
    for name in ("summary.json", "env.json"):
        path = root / "evidence/benchmark/baseline_1m" / name
        document = json.loads(path.read_text(encoding="utf-8"))
        document["replacement_measurements"] = active
        document["post_run_power_audit_scope"] = "Original session; affected backup and pgbench now superseded by separate AC replacement"
        write_json(path, document)
    path = root / "evidence/benchmark/session_1m_crosscheck.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["superseded_phases"] = ["backup_restore_1m", "crosscheck_pgbench"]
    document["replacement_measurements"] = active
    write_json(path, document)
    return active


def run():
    session = "ac_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw, evidence = replacement_paths(session)
    raw.mkdir(parents=True, exist_ok=False)
    evidence.mkdir(parents=True, exist_ok=False)
    before = {name: file_hash(ROOT / name) for name in PROTECTED_FILES}
    report = {"session": session, "status": "STARTED", "started_at_utc": utc_now(), **provenance(),
              "scope": "baseline_1m backup/restore 3 runs; pgbench baseline_100k 3x60s, 8 clients/threads, 10s warmup, seed42, prepared, no TLS",
              "workload_21_runs_repeated": False, "automatic_retries": 0,
              "disk_free_bytes_before": require_disk_space(), "protected_files_sha256_before": before}
    write_json(evidence / "session.json", report)
    if running_containers() != ["pg-dpr"]:
        raise ValueError("Expected only pg-dpr running")
    monitor = ACMonitor(raw, evidence)
    monitor.start()
    try:
        history = archive_originals(session)
        report["historical_manifest"] = (history / "manifest.json").relative_to(ROOT).as_posix()
        for phase in ("backup_restore_1m", "pgbench_crosscheck_100k"):
            monitor.require_ac()
            require_disk_space()
            started = time.perf_counter()
            print(json.dumps({"phase": phase, "status": "starting", "at_utc": utc_now()}), flush=True)
            if phase == "backup_restore_1m":
                backup = backup_restore(runs=3, keep=False, database="baseline_1m", session=session, power_guard=monitor.require_ac)
                status = backup["status"]
            else:
                pgbench = crosscheck(runs=3, duration=60, concurrency=8, session=session, power_guard=monitor.require_ac)
                pgbench["code_commit"] = report.get("code_commit")
                pgbench["targets_commit"] = report.get("targets_commit")
                status = pgbench["status"]
            report[phase] = {"status": status, "elapsed_s": time.perf_counter() - started}
            write_json(evidence / "session.json", report)
            if status != "PASSED":
                raise ValueError("Replacement phase integrity failed")
    except Exception as error:
        report.update(status="FAILED", error_type=type(error).__name__, private_details_withheld=True)
        raise
    finally:
        try:
            power = monitor.finish()
            report["power_qualified"] = power["qualified"]
        finally:
            report["completed_at_utc"] = utc_now()
            write_json(evidence / "session.json", report)
    if not power["qualified"] or any(file_hash(ROOT / name) != digest for name, digest in before.items()):
        report["status"] = "FAILED_POWER_OR_PRESERVATION"
        write_json(evidence / "session.json", report)
        raise ValueError("Power verification/preservation failed; measurements retained without promotion")
    active = promote(session, backup, pgbench, power, history)
    report.update(status="PASSED", protected_files_unchanged=True, active_measurements=active,
                  disk_free_bytes_after=require_disk_space())
    write_json(evidence / "session.json", report)
    print(json.dumps({"status": "PASSED", "session": session, "backup_restore_medians": backup["medians"],
                      "pgbench_medians": pgbench["median_between_runs"], "power_samples": power["samples"]}), flush=True)
    return report


if __name__ == "__main__":
    try:
        run()
    except Exception:
        raise SystemExit("AC replacement failed; safe session evidence retained; no automatic retry or promotion") from None
