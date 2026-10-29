import copy
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from benchmark import ac_monitor, common, power_incident, replacement_ac
from benchmark import backup_restore as backup
from benchmark import pgbench_crosscheck as pg
from benchmark.tests.test_sessions_cli_backup import STATE
from benchmark.tests.test_1m_crosscheck import test_crosscheck_three_runs_share_original_keys_and_cleanup as _existing_crosscheck_case

SESSION = "ac_20261027T150000Z"


def events(online=True, window=None):
    return {"latest_event_at_or_before_start": {"ac_online": online}, "events_in_window": window or []}


def test_paths_and_ac_qualification_fail_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(common, "ROOT", tmp_path)
    raw, evidence = common.replacement_paths(SESSION)
    assert raw.is_relative_to(tmp_path / "results/bench/replacements")
    assert evidence.is_relative_to(tmp_path / "evidence/benchmark/replacements")
    with pytest.raises(ValueError):
        common.replacement_paths("../overwrite")
    assert ac_monitor.qualify([{"ac_online": True}], events())["qualified"]
    for samples, e in (([], events()), ([{"ac_online": None}], events()), ([{"ac_online": True}], events(False)),
                       ([{"ac_online": True}], events(window=[{"ac_online": False}]))):
        assert not ac_monitor.qualify(samples, e)["qualified"]


def test_monitor_and_kernel_reader(monkeypatch, tmp_path):
    monkeypatch.setattr(ac_monitor.psutil, "sensors_battery", lambda: SimpleNamespace(power_plugged=True))
    process = MagicMock(return_value=SimpleNamespace(stdout=json.dumps(events())))
    monkeypatch.setattr(ac_monitor.subprocess, "run", process)
    assert ac_monitor.power_events("2026-10-27T15:00:00+00:00", "2026-10-27T15:01:00+00:00") == events()
    assert "read_power_window.ps1" in " ".join(process.call_args.args[0])
    with pytest.raises(ValueError):
        ac_monitor.power_events("2026-10-27T15:00:00", "2026-10-27T15:01:00")
    monkeypatch.setattr(ac_monitor, "power_events", lambda *a: events())
    monkeypatch.setattr(ac_monitor.time, "sleep", lambda *a: None)
    monitor = ac_monitor.ACMonitor(tmp_path / "raw", tmp_path / "evidence", interval=.01)
    monitor.start()
    monitor.require_ac()
    result = monitor.finish()
    assert result["qualified"] and result["samples"] >= 3
    assert (tmp_path / "raw/ac_samples.csv").exists()
    assert (tmp_path / "raw/ac_all_samples.json").exists()
    monkeypatch.setattr(ac_monitor.psutil, "sensors_battery", lambda: None)
    with pytest.raises(ValueError):
        monitor.require_ac()
    assert monitor.sample()["ac_online"] is None


def test_archive_byte_preservation_and_promote_requires_complete_ac(monkeypatch, tmp_path):
    monkeypatch.setattr(common, "ROOT", tmp_path)
    monkeypatch.setattr(replacement_ac.subprocess, "check_output", lambda *a, **k: "fixture-code\n")
    for name in replacement_ac.OLD_FILES:
        path = tmp_path / "evidence/benchmark" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"old_fixture": name}))
    history = replacement_ac.archive_originals(SESSION, tmp_path)
    manifest = json.loads((history / "manifest.json").read_text())
    assert manifest["label"] == "terdampak baterai"
    for name in replacement_ac.OLD_FILES:
        assert (history / name).read_bytes() == (tmp_path / "evidence/benchmark" / name).read_bytes()
    with pytest.raises(FileExistsError):
        replacement_ac.archive_originals(SESSION, tmp_path)
    backup_report = {"status": "PASSED", "runs": [{"run": 1, "backup_s": 1., "restore_s": 2.}], "medians": {"backup_s": 1., "restore_s": 2.}}
    pg_report = {"status": "PASSED", "runs": [{"run": 1, "p50_ms": .1, "p95_ms": .2, "throughput_rps": 100., "errors": 0}], "median_between_runs": {"p50_ms": .1}}
    with pytest.raises(ValueError):
        replacement_ac.promote(SESSION, backup_report, pg_report, {"qualified": False}, history, tmp_path)
    original_workload = {"original_21_run_metrics": [1, 2, 3]}
    (tmp_path / "evidence/benchmark/baseline_1m/summary.json").write_text(json.dumps(original_workload))
    active = replacement_ac.promote(SESSION, backup_report, pg_report, {"qualified": True}, history, tmp_path)
    summary = json.loads((tmp_path / "evidence/benchmark/baseline_1m/summary.json").read_text())
    assert summary["original_21_run_metrics"] == [1, 2, 3] and not active["workload_21_runs_repeated"]
    assert json.loads((tmp_path / "evidence/benchmark/crosscheck_pgbench.json").read_text())["measurement_label"] == "pengukuran pengganti AC"
    historical = power_incident.historical_measurement(tmp_path / "evidence/benchmark/crosscheck_pgbench.json", tmp_path)
    assert historical == {"old_fixture": "crosscheck_pgbench.json"}
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"original_battery_affected_evidence": "../escape.json"}))
    with pytest.raises(ValueError):
        power_incident.historical_measurement(bad, tmp_path)


def test_replacement_backup_paths_three_runs_and_guard(monkeypatch, tmp_path, source):
    monkeypatch.setattr(common, "ROOT", tmp_path)
    monkeypatch.setattr(common, "require_disk_space", lambda: 20_000_000_000)
    monkeypatch.setattr(backup, "private_directory", lambda: tmp_path)
    monkeypatch.setattr(backup, "state", lambda *a, **k: dict(STATE))
    monkeypatch.setattr(backup, "source_rows", lambda: source)
    monkeypatch.setattr(backup, "provenance", lambda: {})
    monkeypatch.setattr(backup, "parameters", lambda *a, **k: {})
    monkeypatch.setattr(backup, "running_containers", lambda: ["pg-dpr"])
    monkeypatch.setattr(backup.psycopg, "connect", MagicMock())
    def call(cmd, **kwargs):
        if "pg_dump" in cmd:
            kwargs["stdout"].write(b"PGDMP-fixture")
    monkeypatch.setattr(backup.subprocess, "run", call)
    guard = MagicMock()
    report = backup.backup_restore(database="baseline_1m", session=SESSION, power_guard=guard)
    assert len(report["runs"]) == 3 and guard.call_count == 9
    assert all("restore_completed_at_utc" in row for row in report["runs"])
    assert (tmp_path / "evidence/benchmark/replacements" / SESSION / "baseline_1m/backup_restore.json").exists()
    assert not (tmp_path / "evidence/benchmark/baseline_1m/backup_restore.json").exists()
    with pytest.raises(ValueError):
        backup.backup_restore(database="baseline_100k", session=SESSION)


def test_whole_replacement_orchestration_never_calls_workload(monkeypatch, tmp_path):
    monkeypatch.setattr(common, "ROOT", tmp_path)
    monkeypatch.setattr(replacement_ac, "ROOT", tmp_path)
    for name in replacement_ac.PROTECTED_FILES:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture unchanged")
    monkeypatch.setattr(replacement_ac, "require_disk_space", lambda: 20_000_000_000)
    monkeypatch.setattr(replacement_ac, "provenance", lambda: {})
    monkeypatch.setattr(replacement_ac, "running_containers", lambda: ["pg-dpr"])
    monitor = MagicMock()
    monitor.finish.return_value = {"qualified": True, "samples": 10}
    monkeypatch.setattr(replacement_ac, "ACMonitor", lambda *a: monitor)
    monkeypatch.setattr(replacement_ac, "archive_originals", lambda s: tmp_path / "evidence/history")
    backup_call = MagicMock(return_value={"status": "PASSED", "medians": {"backup_s": 1}})
    pg_call = MagicMock(return_value={"status": "PASSED", "median_between_runs": {"p50_ms": .1}})
    monkeypatch.setattr(replacement_ac, "backup_restore", backup_call)
    monkeypatch.setattr(replacement_ac, "crosscheck", pg_call)
    monkeypatch.setattr(replacement_ac, "promote", lambda *a: {"workload_21_runs_repeated": False})
    result = replacement_ac.run()
    assert result["status"] == "PASSED" and not result["workload_21_runs_repeated"]
    assert backup_call.call_args.kwargs["database"] == "baseline_1m" and backup_call.call_args.kwargs["runs"] == 3
    assert pg_call.call_args.kwargs["duration"] == 60 and pg_call.call_args.kwargs["concurrency"] == 8
    assert backup_call.call_count == pg_call.call_count == 1
    assert "baseline_run" not in replacement_ac.__dict__


def test_crosscheck_replacement_keeps_old_file_and_uses_same_three_runs(monkeypatch, tmp_path, source):
    monkeypatch.setattr(common, "ROOT", tmp_path)
    old = tmp_path / "evidence/benchmark/crosscheck_pgbench.json"
    old.parent.mkdir(parents=True)
    old.write_text('"old battery result"')
    original = pg.crosscheck
    guard = MagicMock()
    def redirected(*args, **kwargs):
        return original(*args, session=SESSION, power_guard=guard, **kwargs)
    monkeypatch.setattr(pg, "crosscheck", redirected)
    _existing_crosscheck_case(monkeypatch, tmp_path, source, False)
    assert guard.call_count == 9 and old.read_text() == '"old battery result"'
    assert (tmp_path / "evidence/benchmark/replacements" / SESSION / "crosscheck_pgbench.json").exists()


def test_monitor_collection_failure_cannot_qualify(monkeypatch, tmp_path):
    monkeypatch.setattr(ac_monitor.psutil, "sensors_battery", lambda: SimpleNamespace(power_plugged=True))
    monkeypatch.setattr(ac_monitor, "power_events", lambda *a: events())
    monkeypatch.setattr(ac_monitor.time, "sleep", lambda *a: None)
    monitor = ac_monitor.ACMonitor(tmp_path / "missing/raw", tmp_path / "evidence")
    monitor.started_at = "2026-10-27T15:00:00+00:00"
    monitor.collect()
    assert monitor.collection_failure == "FileNotFoundError"
    with pytest.raises(ValueError):
        monitor.require_ac()
    assert not monitor.finish()["qualified"]
