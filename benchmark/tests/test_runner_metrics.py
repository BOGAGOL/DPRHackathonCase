from collections import Counter
from itertools import islice
import json
from types import SimpleNamespace
from unittest.mock import MagicMock
import time

import pytest

from benchmark import collect_metrics as cm
from benchmark import runner


MANIFEST = {"seed":42,"scenarios":["read_by_nik","read_by_email","read_profile","list_page","update_contact","insert_member","mixed"],
            "mixed_cycle":{"read_by_nik":20,"read_by_email":20,"read_profile":20,"list_page":10,"update_contact":15,"insert_member":15}}


def test_cycle_exact_70_30_and_reproducible():
    cycle = list(islice(runner.operation_cycle("mixed", MANIFEST, 0), 100))
    assert Counter(cycle) == MANIFEST["mixed_cycle"]
    assert cycle == list(islice(runner.operation_cycle("mixed", MANIFEST, 0), 100))
    assert list(islice(runner.operation_cycle("read_profile", MANIFEST, 0), 2)) == ["read_profile"]*2
    with pytest.raises(ValueError):
        next(runner.operation_cycle("mixed", dict(MANIFEST,mixed_cycle={}), 0))


def test_memory_docker_and_collector(monkeypatch, tmp_path):
    assert cm.memory_bytes("1.5MiB") == 1572864
    assert cm.memory_bytes("2GB") == 2000000000
    with pytest.raises(ValueError):
        cm.memory_bytes("unavailable")
    monkeypatch.setattr(cm.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=json.dumps({"CPUPerc":"12.5%","MemUsage":"4MiB / 8GiB"})))
    assert cm.docker_sample()["db_ram_bytes"] == 4194304
    collector = cm.Collector(tmp_path / "metrics.csv", interval=.001)
    collector.start()
    time.sleep(.03)
    result = collector.finish()
    assert result["samples"] > 0 and result["failed_samples"] == 0
    assert result["db_cpu_percent_one_core_median"] == 12.5
    failed = cm.Collector(tmp_path / "failed.csv", interval=.001)
    monkeypatch.setattr(cm, "docker_sample", MagicMock(side_effect=RuntimeError("private error withheld")))
    failed.start(); time.sleep(.02)
    result = failed.finish()
    assert result["failed_samples"] > 0 and result["db_ram_bytes_median"] is None
    assert "private error" not in (tmp_path / "failed.csv").read_text()


def test_eight_workers_timing_raw_and_errors(monkeypatch, tmp_path):
    collector = MagicMock(); collector.thread = None
    collector.finish.return_value = {"samples":1,"failed_samples":0}
    monkeypatch.setattr(runner, "Collector", lambda *a: collector)
    adapter = MagicMock()
    def execute(conn, operation, key, worker):
        time.sleep(.0005)
        if worker == 0:
            raise ValueError("sensitive payload must never appear")
    adapter.execute.side_effect = execute
    result = runner.one_run(adapter,"mixed",1,MANIFEST,8,.08,.02,tmp_path / "run")
    assert result["requests"] > 8 and result["errors"] > 0 and result["warmup_errors"] > 0
    assert result["elapsed_s"] >= .08 and result["concurrency"] == 8
    assert len(list((tmp_path / "run").glob("requests_worker_*.csv"))) == 8
    assert all("sensitive payload" not in p.read_text() for p in (tmp_path / "run").glob("*.csv"))
    assert adapter.connect.call_count == 8


def test_runner_preflight_guards(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "RAW", tmp_path)
    with pytest.raises(ValueError):
        runner.baseline_run(runs=1)
    monkeypatch.setattr(runner, "running_containers", lambda: ["pg-dpr","another"])
    with pytest.raises(ValueError):
        runner.baseline_run()
    (tmp_path / "env.json").write_text("{}")
    with pytest.raises(ValueError):
        runner.baseline_run()
