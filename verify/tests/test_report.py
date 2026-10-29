"""Readable results must retain failures/scopes and agree with measured output."""
import copy
import csv
from pathlib import Path
import shutil

import pytest

from verify import report


def test_report_contains_measured_results_and_explicit_limits():
    data = report.load(report.ROOT)
    rendered = report.render(data)
    assert len(data["benchmarks"]) == 28
    assert len([r for r in data["benchmarks"] if r["variant"] == "v2"]) == 14
    assert "TARGET LATENSI / THROUGHPUT BELUM TERCAPAI" in rendered
    assert "bukan waktu respons web publik" in rendered
    assert "https://43.156.157.247/login" in rendered
    assert "accounts.md" in rendered
    assert "Login browser deployment belum lulus" in rendered
    assert "95% permintaan" in rendered and "scope" in rendered
    assert "<script" not in rendered


def test_untrusted_metric_labels_are_escaped():
    data = report.load(report.ROOT)
    data["benchmarks"][0]["scenario"] = '<script>alert("invented")</script>'
    # Table includes v2 only; use a measured v2 row for this output boundary.
    next(r for r in data["benchmarks"] if r["variant"] == "v2")["scenario"] = '<script>invented</script>'
    rendered = report.render(data)
    assert "<script>" not in rendered and "&lt;script&gt;invented" in rendered


def test_mismatched_derived_latency_refuses_report(tmp_path):
    source = report.ROOT / "docs/data/db-benchmark.csv"
    destination = tmp_path / "docs/data/db-benchmark.csv"
    destination.parent.mkdir(parents=True)
    rows = report.read_csv(source)
    rows[0]["B_p95_ms"] = "999999"
    with destination.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    original = report.ROOT / "evidence/benchmark/bppb_100k/summary.json"
    target = tmp_path / "evidence/benchmark/bppb_100k/summary.json"
    target.parent.mkdir(parents=True)
    shutil.copyfile(original, target)
    with pytest.raises(ValueError, match="differs"):
        report.load(tmp_path)


def test_execution_page_is_readable_and_does_not_call_not_run_pass():
    page = report.run_page({"passed": False, "transport": "native", "stages": {
        "setup": {"status": "PASS"}, "hardening": {"status": "FAIL"}, "service_application": {"status": "NOT_RUN"}}})
    assert "GAGAL" in page and "NOT_RUN" in page and "summary.json" in page
    assert "belum dijalankan" in page
    assert report.number(12.3456) == "12.35"
    assert "&lt;" in report.table(("<unsafe>",), (("<unsafe>",),))


def test_offline_command_writes_report(tmp_path, capsys):
    output = tmp_path / "results.html"
    assert report.main(["--output", str(output)]) == 0
    assert "Pelindungan Data" in output.read_text(encoding="utf-8")
    assert "Hasil dapat dibaca" in capsys.readouterr().out
