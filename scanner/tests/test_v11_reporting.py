import csv
from html.parser import HTMLParser
import json

from scanner import CHANGE_SUMMARY, __version__
from scanner.__main__ import main
from scanner.reporting import emit, minimal_anonymity, ordered_anonymity


def k_result(columns, unique, total=100, table="fixture"):
    return {"table": table, "columns": columns, "unique_rows": unique, "total_rows": total,
            "k_min": 1 if unique else 2, "groups": unique, "scope": "full_fixture"}


def test_k_order_minimal_then_unique_counts():
    results = [k_result(["a", "b", "c"], 99), k_result(["a", "b"], 90),
               k_result(["b"], 30), k_result(["a"], 60), k_result(["b", "c"], 95)]
    ordered = ordered_anonymity(results)
    assert [r["columns"] for r in ordered] == [["a"], ["b"], ["b", "c"], ["a", "b"], ["a", "b", "c"]]


def test_k_supersets_hidden_only_at_threshold_and_same_table():
    rows = [k_result(["a"], 95), k_result(["a", "b"], 99), k_result(["b"], 94),
            k_result(["b", "c"], 99), k_result(["a", "b", "c"], 100),
            k_result(["a", "b"], 99, table="other"), k_result(["empty"], 0, total=0)]
    shown = minimal_anonymity(rows)
    assert not any(r["table"] == "fixture" and r["columns"] == ["a", "b"] for r in shown)
    assert any(r["columns"] == ["b", "c"] for r in shown)
    assert not any(r["columns"] == ["a", "b", "c"] for r in shown)
    assert any(r["table"] == "other" for r in shown)
    assert any(r["total_rows"] == 0 for r in shown)
    assert len(rows) == 7  # original aggregate results are retained


class ReportParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = None
        self.depth = 0
        self.k_rows = 0
        self.summary_headers = []
        self.summary_before_detail = False
        self.tables_seen = []
        self.in_header = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table":
            self.active = attrs.get("id") or attrs.get("class")
            self.tables_seen.append(self.active)
        if tag == "tr" and self.active == "k-anonymity-table":
            self.k_rows += 1
        if tag == "th" and self.active == "summary":
            self.in_header = True

    def handle_endtag(self, tag):
        if tag == "table":
            self.active = None
        if tag == "th":
            self.in_header = False

    def handle_data(self, data):
        if self.in_header:
            self.summary_headers.append(data)


def test_report_caps_html_preserves_all_json_and_prints_landscape(tmp_path):
    rows = [k_result([f"q_{i:02d}"], i) for i in range(20)]
    emit(tmp_path, [], {}, {}, rows, label="before", source={}, sample=1000, duration=0)
    aggregates = json.loads((tmp_path / "k_anonymity.json").read_text())
    assert len(aggregates) == 20
    assert [r["unique_rows"] for r in aggregates] == list(reversed(range(20)))
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    parsed = ReportParser()
    parsed.feed(html)
    assert parsed.k_rows == 16  # header plus 15 findings
    assert parsed.summary_headers == ["column", "detected_type", "pdp_class", "priority", "triage",
                                      "recommendation", "consistent_protection_with"]
    assert parsed.tables_seen.index("summary") < parsed.tables_seen.index("detail")
    assert "size:A4 landscape" in html
    assert "display:table-header-group" in html
    assert "td.reason{white-space:normal" in html
    assert "overflow:visible" in html


def test_superset_retained_in_json_but_not_html(tmp_path):
    rows = [k_result(["dob"], 95), k_result(["dob", "city"], 100)]
    emit(tmp_path, [], {}, {}, rows, label="before", source={}, sample=1000, duration=0)
    assert len(json.loads((tmp_path / "k_anonymity.json").read_text())) == 2
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "dob + city" not in html


def test_run_metadata_and_single_birth_uniqueness(sql_dump, tmp_path):
    out = tmp_path / "v11"
    assert main(["dump", "--file", str(sql_dump), "--out", str(out)]) == 0
    meta = json.loads((out / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["scanner_version"] == __version__ == "1.2.0"
    assert meta["change_summary"] == CHANGE_SUMMARY
    assert all(isinstance(change, str) and change for change in meta["change_summary"])
    with (out / "inventory.csv").open(encoding="utf-8", newline="") as handle:
        inventory = list(csv.DictReader(handle))
    dob = next(r for r in inventory if r["column"] == "tanggal_lahir")
    assert "k-anonymity satu kolom: 24 dari 24 baris unik (k=1)" in dob["reason"]
    assert dob["recommendation"] == "generalize_for_analyst"
    assert "consistent_protection_with" in dob
    html = (out / "report.html").read_text(encoding="utf-8")
    assert dob["reason"] in html


def test_missing_k_measurement_is_explicit(tmp_path):
    # Unstructured files mode cannot compute a whole-table date aggregate.
    path = tmp_path / "date.log"
    path.write_text("1988-06-01\n1988-06-02\n")
    out = tmp_path / "out"
    assert main(["files", str(path), "--out", str(out)]) == 0
    with (out / "inventory.csv").open(encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    assert row["detected_type"] == "tanggal_lahir"
    assert "k-anonymity satu kolom belum tersedia" in row["reason"]
