import json
import secrets
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import quote

import pytest

from benchmark import common
from benchmark.stats import percentile, summarize, medians


def test_percentiles_linear_and_median_between_runs():
    assert percentile([10, 0], .95) == 9.5
    assert percentile([1], .5) == 1
    assert percentile([4, 2, 8, 6], .5) == 5
    reports = [summarize([1, 2, x], 1, 2) for x in (100, 4, 8)]
    assert medians(reports)["p95_ms"] == sorted(r["p95_ms"] for r in reports)[1]
    assert reports[0]["throughput_rps"] == 1 and reports[0]["error_rate"] == 1/3
    assert medians(reports)["p95_ms"] != percentile([1,2,100,1,2,4,1,2,8], .95)
    for values, quantile in (([], .5), ([1], 2)):
        with pytest.raises(ValueError):
            percentile(values, quantile)
    with pytest.raises(ValueError):
        summarize([], 0, 1)
    with pytest.raises(ValueError):
        medians([])


def test_environment_guards_and_private_storage(monkeypatch, tmp_path):
    secret = secrets.token_urlsafe(32)
    monkeypatch.setenv("BENCH_DATABASE_URL", f"postgresql://bench_user:{quote(secret)}@127.0.0.1:5433/baseline_100k")
    monkeypatch.setenv("DATAGEN_DATABASE_URL", f"postgresql://postgres:{quote(secret)}@127.0.0.1:5433/postgres")
    assert common.parameters()["sslmode"] == "disable"
    assert common.parameters("bench_restore_1_0123456789ab", True)["dbname"].startswith("bench_restore_")
    with pytest.raises(ValueError):
        common.parameters("postgres")
    with pytest.raises(ValueError):
        common.parameters("protected_100k", True)
    monkeypatch.setenv("BENCH_DATABASE_URL", "postgresql://bench_user@localhost:5433/baseline_100k")
    with pytest.raises(ValueError):
        common.parameters()
    monkeypatch.delenv("BENCH_DATABASE_URL")
    with pytest.raises(ValueError):
        common.parameters()
    monkeypatch.setenv("DPR_PRIVATE_DIR", str(common.ROOT / "private"))
    with pytest.raises(ValueError):
        common.private_directory()
    monkeypatch.setenv("DPR_PRIVATE_DIR", str(tmp_path))
    assert common.private_directory() == tmp_path / "benchmark"
    monkeypatch.delenv("DPR_PRIVATE_DIR")
    with pytest.raises(ValueError):
        common.private_directory()


def test_output_helpers_and_container_names(monkeypatch, tmp_path):
    path = tmp_path / "summary.json"
    common.write_json(path, {"count": 100})
    assert json.loads(path.read_text())["count"] == 100 and len(common.file_hash(path)) == 64
    common.write_csv(tmp_path / "summary.csv", [{"count": 100}])
    with pytest.raises(ValueError):
        common.write_csv(tmp_path / "empty.csv", [])
    assert "+00:00" in common.utc_now()
    monkeypatch.setattr(common.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="pg-dpr\n"))
    assert common.running_containers() == ["pg-dpr"]


def test_read_only_state_and_sequence_checksum(monkeypatch, source):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.execute.return_value.fetchone.side_effect = [{"n": 40}, {"last_value": 40, "is_called": True}, {"database_bytes": 100}]
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.__iter__.return_value = iter(source)
    monkeypatch.setattr(common, "parameters", lambda *a: {})
    monkeypatch.setattr(common.psycopg, "connect", lambda **k: conn)
    result = common.state()
    assert result["rows"] == 40 and "READ ONLY" in conn.execute.call_args_list[0].args[0]
    assert common.same_data(result, dict(result, storage={"database_bytes": 200}))
    assert not common.same_data(result, dict(result, sequence={"last_value": 41, "is_called": True}))
