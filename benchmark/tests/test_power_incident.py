from datetime import datetime, timedelta, timezone
import gzip
import json
from pathlib import Path

import pytest

from benchmark import power_incident as audit


def event(at, online, record):
    return {"event_id": 105, "record_id": record, "time_utc": at, "time_wib": at, "data": {"AcOnline": online}}


def test_power_state_pairing_and_boundary_overlap():
    events = [event("2026-10-27T19:27:00+07:00", "true", 3),
              event("2026-10-27T19:18:00+07:00", "false", 2),
              event("2026-10-27T18:15:00+07:00", "true", 1)]
    intervals = audit.battery_intervals(events)
    assert len(intervals) == 1 and intervals[0]["duration_s"] == 540
    assert audit.overlap(audit.timestamp("2026-10-27T19:17:00+07:00"), audit.timestamp("2026-10-27T19:18:00+07:00"), intervals[0]) == 0
    assert audit.overlap(audit.timestamp("2026-10-27T19:17:00+07:00"), audit.timestamp("2026-10-27T19:19:00+07:00"), intervals[0]) == 60
    with pytest.raises(ValueError):
        audit.timestamp("2026-10-27T19:00:00")
    with pytest.raises(ValueError):
        audit.battery_intervals([event("2026-10-27T19:00:00+07:00", "unknown", 4)])


def test_resource_read_and_missing_is_not_zero(tmp_path):
    path = tmp_path / "resources.csv.gz"
    text = ("timestamp_utc,db_cpu_percent_one_core,client_cpu_percent_one_core,db_ram_bytes,client_ram_bytes,ok\n"
            "2026-10-27T19:00:00+07:00,80,120,1000,2000,True\n")
    with gzip.open(path, "wt") as handle:
        handle.write(text)
    rows = audit.resource_rows(path)
    assert audit.resource_summary(rows)["client_cpu_percent_one_core_median"] == 120
    assert audit.resource_summary([])["client_cpu_percent_one_core_median"] is None
    assert audit.resource_summary([{**rows[0], "ok": "False"}])["failed"] == 1
    plain = tmp_path / "resources.csv"
    plain.write_text(text)
    assert audit.resource_rows(plain) == rows


def test_run_comparison_not_confusing_completed_time_with_measurement_end():
    runs = [{"scenario": "fixture", "run": i, "started_at_utc": f"2026-10-27T19:0{i}:00+07:00",
             "elapsed_s": 60, "completed_at_utc": f"2026-10-27T19:2{i}:00+07:00", "warmup_s": 10,
             "p50_ms": 1.0 * i, "p95_ms": 2.0 * i, "throughput_rps": 100.0 * i, "errors": 0} for i in (1, 2, 3)]
    interval = {"start_wib": "2026-10-27T19:18:00+07:00", "end_wib": "2026-10-27T19:27:00+07:00"}
    result = audit.analyze_runs(runs, {("fixture", i): [] for i in (1, 2, 3)}, interval)
    assert all(row["confirmed_battery_overlap_s"] == 0 for row in result)
    assert all(row["confirmed_incident_resource_samples"] == 0 for row in result)
    assert result[0]["ended_at_wib"] == "2026-10-27T19:02:00+07:00"
    assert result[0]["comparisons"]["p50_ms"]["other_two_runs_median"] == 2.5
    assert result[0]["comparisons"]["p50_ms"]["difference_percent"] == -60


def test_pgbench_uses_raw_transaction_clock_and_secondary_phase_overlap(tmp_path):
    folder = tmp_path / "run_1"
    folder.mkdir()
    start = audit.timestamp("2026-10-27T19:20:00+07:00").timestamp()
    (folder / "fixture.log").write_text(f"0 1 100 0 {int(start)} 0\n0 2 120 0 {int(start+60)} 0\n")
    first, last = audit.pgbench_bounds(folder)
    assert (last - first).total_seconds() == 60
    backup = {"runs": [{"run": 1, "started_at_utc": "2026-10-27T19:17:15+07:00", "backup_s": 24, "restore_s": 28}]}
    pgbench = {"runs": [{"run": 1, "p50_ms": .1, "p95_ms": .2, "throughput_rps": 100, "errors": 0}]}
    result = audit.secondary_phases(backup, pgbench, tmp_path, {"start_wib": "2026-10-27T19:18:04+07:00", "end_wib": "2026-10-27T19:27:03+07:00"})
    assert result["backup_restore"][0]["backup_battery_overlap_approx_s"] == 0
    assert result["backup_restore"][0]["restore_battery_overlap_approx_s"] == 3
    assert result["pgbench_crosscheck"][0]["observed_transaction_span_battery_overlap_s"] == 60


def test_full_offline_analysis_and_annotation_preserves_original_metrics(monkeypatch, tmp_path):
    # Use copied, tiny synthetic metadata/logs only: no benchmark or DB execution.
    root = tmp_path
    directory = root / "evidence/benchmark/baseline_1m"
    directory.mkdir(parents=True)
    events = [event("2026-10-27T19:18:00+07:00", "false", 2), event("2026-10-27T19:27:00+07:00", "true", 3)]
    (directory / "power_events.json").write_text(json.dumps({"events": events}))
    runs = [{"scenario": "fixture", "run": i, "started_at_utc": f"2026-10-27T19:0{i}:00+07:00",
             "elapsed_s": 60, "completed_at_utc": f"2026-10-27T19:0{i+1}:00+07:00", "warmup_s": 10,
             "p50_ms": 1., "p95_ms": 2., "throughput_rps": 100., "errors": 0} for i in (1, 2, 3)]
    backup = {"runs": [{"run": 1, "started_at_utc": "2026-10-27T19:19:00+07:00", "backup_s": 20, "restore_s": 25}], "medians": {"backup_s": 20, "restore_s": 25}}
    pgbench = {"runs": [{"run": 1, "p50_ms": .1, "p95_ms": .2, "throughput_rps": 1000, "errors": 0}], "comparability_limits": []}
    docs = {directory / "env.json": {"power_plugged_verified": True}, directory / "run_summaries.json": runs,
            directory / "summary.json": {"metric": 1}, directory / "backup_restore.json": backup,
            root / "evidence/benchmark/crosscheck_pgbench.json": pgbench,
            root / "evidence/benchmark/session_1m_crosscheck.json": {"status": "PASSED"}}
    for path, data in docs.items():
        path.write_text(json.dumps(data))
    monkeypatch.setattr(audit, "resource_rows", lambda p: [])
    monkeypatch.setattr(audit, "pgbench_bounds", lambda p: (audit.timestamp("2026-10-27T19:22:00+07:00"), audit.timestamp("2026-10-27T19:23:00+07:00")))
    monkeypatch.setattr(audit.subprocess, "check_output", lambda *a, **k: "fixture-commit\n")
    report = audit.run(root)
    assert report["conclusion"]["workload_runs_confirmed_overlap"] == 0
    assert len(report["workload_runs"]) == 3
    audit.annotate_metadata(report, root)
    updated = json.loads((directory / "run_summaries.json").read_text())
    for old, new in zip(runs, updated):
        assert all(new[key] == value for key, value in old.items())
    assert json.loads((directory / "backup_restore.json").read_text())["medians"] == backup["medians"]
    assert json.loads((directory / "env.json").read_text())["power_plugged_verified"] is True
    assert (directory / "power_run_timeline.csv").exists()
    audit.annotate_metadata(report, root)
    assert len(json.loads((root / "evidence/benchmark/crosscheck_pgbench.json").read_text())["comparability_limits"]) == 1
