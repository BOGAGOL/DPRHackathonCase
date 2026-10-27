"""Machine summaries must not echo failure payloads or operational secrets."""
import importlib.util
import json
from pathlib import Path
import secrets


def load_exporter():
    path = Path(__file__).with_name("export_results.py")
    spec = importlib.util.spec_from_file_location("module_b_test_result_exporter", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_summary_excludes_failure_text_and_counts_actual_outcomes(tmp_path):
    canary = secrets.token_urlsafe(24)
    source = tmp_path / "local-junit.xml"
    source.write_text('<testsuites><testsuite><testcase name="pass" classname="access" time="0.1"/>'
                      '<testcase name="fail" classname="access" time="0.2"><failure message="' + canary + '">' + canary + '</failure></testcase>'
                      '<testcase name="skip" classname="scope" time="0"><skipped message="' + canary + '"/></testcase>'
                      '</testsuite></testsuites>', encoding="utf-8")
    result = load_exporter().summarize(source)
    assert result["status"] == "FAILED" and result["total"] == 3
    assert result["counts"] == {"passed": 1, "failed": 1, "skipped": 1}
    assert canary not in json.dumps(result)


def test_empty_evidence_cannot_be_reported_pass(tmp_path):
    source = tmp_path / "empty.xml"
    source.write_text("<testsuites/>", encoding="utf-8")
    assert load_exporter().summarize(source)["status"] == "FAILED"
