from unittest.mock import MagicMock

import pytest

from benchmark import diagnose_overhead as diagnostic


def test_distribution_and_plan_privacy():
    assert diagnostic.distribution([1., 2., 3.])["mean_ms"] == 2
    result = diagnostic.sanitize_explain([{"Planning Time": .02, "Execution Time": .04,
        "Plan": {"Node Type": "Index Scan", "Index Name": "test_index", "Index Cond": "secret",
                 "Plans": [{"Output": "secret"}], "Shared Hit Blocks": 4}}])
    assert "secret" not in str(result)
    assert result["execution_ms"] == .04 and result["Shared Read Blocks"] == 0


def test_driver_wrapper_and_worker_persistent_connection(tmp_path):
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = [("synthetic",)]
    conn.execute.return_value.fetchone.return_value = (1,)
    proxy = diagnostic.TimedConnection(conn)
    assert proxy.execute("bound", (1,)).fetchall() == [("synthetic",)]
    assert proxy.execute_ms >= 0 and proxy.fetch_ms >= 0
    adapter = MagicMock()
    def execute(connection, *args):
        connection.execute("bound", (1,)).fetchall()
    adapter.execute.side_effect = execute
    result = diagnostic.diagnostic_worker(adapter, conn, 0, 4, MagicMock(), tmp_path / "requests.csv")
    assert len(result["samples"]) == 4 and result["persistent_backend_pid_unchanged"]
    assert adapter.execute.call_count == 36
    assert "synthetic" not in (tmp_path / "requests.csv").read_text()


def test_measure_uses_exactly_one_connection_per_worker(tmp_path):
    adapter = MagicMock()
    connections = [MagicMock(), MagicMock()]
    adapter.connect.side_effect = connections
    result = diagnostic.measure(adapter, 2, 4, tmp_path / "raw")
    assert result["connection_count"] == 2 and adapter.connect.call_count == 2
    assert result["requests"] == 4 and result["persistent_backends_verified"]
    for conn in connections:
        assert conn.close.called
    with pytest.raises(ValueError):
        diagnostic.measure(adapter, 3, 4, tmp_path / "bad")


def test_cache_snapshot_and_explain_are_read_only(monkeypatch):
    conn = MagicMock()
    conn.execute.return_value.fetchone.side_effect = [
        (134217728,), (10, 90), (10, 90, None), ("",), (False,), (1024,)]
    conn.execute.return_value.fetchall.return_value = [("idx", 4096, 2, 8)]
    conn.__enter__.return_value = conn
    monkeypatch.setattr(diagnostic, "parameters", lambda *a: {})
    monkeypatch.setattr(diagnostic.psycopg, "connect", lambda **k: conn)
    result = diagnostic.cache_snapshot("baseline_100k")
    assert result["indexes"][0]["hit_ratio"] == .8
    assert result["heap"]["hit_ratio"] == .9
    conn = MagicMock()
    conn.__enter__.return_value = conn
    doc = [{"Planning Time": .01, "Execution Time": .02, "Plan": {"Node Type": "Index Scan", "Index Cond": "private"}}]
    conn.execute.return_value.fetchone.return_value = (doc,)
    adapter = MagicMock(keys={"profiles": [{"no_ktp": "synthetic"}]})
    adapter.connect.return_value = conn
    result = diagnostic.explain_samples(adapter)
    assert result["requests"] == 1 and "private" not in str(result)


def test_run_refuses_missing_corpus(monkeypatch, tmp_path):
    monkeypatch.setattr(diagnostic, "private_directory", lambda: tmp_path)
    with pytest.raises(ValueError, match="corpus"):
        diagnostic.run()
