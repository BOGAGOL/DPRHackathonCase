"""Verify report derivation and fail visibly when facts or source snapshots change."""

import importlib.util
import json
from pathlib import Path
import shutil

import pytest

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def report_copy(tmp_path):
    destination = tmp_path / "report"
    shutil.copytree(
        HERE, destination, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache")
    )
    return destination


def test_current_report_sources_tables_links_and_math():
    result = load("verify_context").validate(HERE, ROOT)
    assert result["passed"], result["errors"]
    assert (
        result["columns"],
        result["benchmark_rows"],
        result["leakage_rows"],
        result["chapters_consolidated"],
    ) == (29, 28, 10, 11)


def test_changed_table_is_rejected(report_copy):
    path = report_copy / "tables/db-benchmark.csv"
    path.write_text(
        path.read_text(encoding="utf-8").replace("naive_v1", "invented", 1),
        encoding="utf-8",
    )
    result = load("verify_context").validate(report_copy)
    assert any(error["kind"] == "table_snapshot_mismatch" for error in result["errors"])


def test_benchmark_target_cannot_be_relabelled_passed(report_copy):
    path = report_copy / "evidence_snapshot.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["db_benchmark"][0]["P01_ratio_passed"] = True
    path.write_text(json.dumps(data), encoding="utf-8")
    result = load("verify_context").validate(report_copy)
    assert any(
        error["kind"] == "benchmark_math_or_target_mismatch"
        for error in result["errors"]
    )


def test_zero_leakage_denominator_is_not_treated_as_success(report_copy):
    path = report_copy / "evidence_snapshot.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["leakage"][0]["ESCE_denominator"] = 0
    path.write_text(json.dumps(data), encoding="utf-8")
    result = load("verify_context").validate(report_copy)
    assert any(
        error["kind"] == "invalid_leakage_denominator_or_ratio"
        for error in result["errors"]
    )


def test_changed_sbom_cannot_reuse_old_schema_validation(report_copy):
    path = report_copy / "appendix/sbom/infrastructure.cdx.json"
    path.write_text("{}", encoding="utf-8")
    result = load("verify_context").validate(report_copy)
    assert any(error["kind"] == "sbom_schema_proof_stale" for error in result["errors"])


def test_inventory_excludes_surrogate_and_replaces_samples():
    scanner = [
        {"column": "id", "sample_masked": "invented id"},
        {
            "column": "nama",
            "sample_masked": "invented source sample",
            "risk_level": "tinggi",
        },
    ]
    columns = [
        {
            "column": "nama",
            "safe_pattern_description": "UTF-8 name shape",
            "truth_pdp_class": "umum",
        }
    ]
    rows = load("build_appendix").inventory_rows(scanner, columns)
    assert len(rows) == 1 and rows[0]["column"] == "nama"
    assert rows[0]["sample_masked"] == "UTF-8 name shape"
    assert "invented source sample" not in json.dumps(rows)
    assert scanner[1]["sample_masked"] == "invented source sample"


def test_copied_access_evidence_tamper_is_rejected(report_copy):
    path = report_copy / "evidence/access-control/analyst_suppression.json"
    path.write_text("{}", encoding="utf-8")
    result = load("verify_context").validate(report_copy)
    assert any(
        error["kind"] == "appendix_evidence_changed" for error in result["errors"]
    )


def test_appendix_text_hash_is_portable_but_raw_hash_is_exact(tmp_path):
    lf, crlf = tmp_path / "lf.txt", tmp_path / "crlf.txt"
    lf.write_bytes(b"invented fixture\n")
    crlf.write_bytes(b"invented fixture\r\n")
    builder = load("build_appendix")
    assert builder.sha(lf, text=True) == builder.sha(crlf, text=True)
    assert builder.sha(lf) != builder.sha(crlf)


def test_changed_source_hash_is_reported(report_copy):
    path = report_copy / "source_manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    name = next(iter(data["source_files"]))
    data["source_files"][name] = "0" * 64
    path.write_text(json.dumps(data), encoding="utf-8")
    result = load("verify_context").validate(report_copy, ROOT)
    assert {"kind": "source_changed", "path": name} in result["errors"]


def test_handoff_links_must_stay_inside_the_report_folder(report_copy):
    path = report_copy / "README.md"
    path.write_text(
        path.read_text(encoding="utf-8") + "\n[Outside](../README.md)\n",
        encoding="utf-8",
    )
    result = load("verify_context").validate(report_copy)
    assert any(
        error["kind"] == "nonlocal_or_missing_link" for error in result["errors"]
    )


def test_updated_chapter_requires_refresh_of_combined_context(report_copy):
    path = report_copy / "02_ANALISIS_DATA_DAN_PRIORITAS.md"
    path.write_text(
        path.read_text(encoding="utf-8") + "\nNew reviewed fact.\n", encoding="utf-8"
    )
    result = load("verify_context").validate(report_copy)
    assert any(
        error["kind"] == "chapter_not_consolidated" for error in result["errors"]
    )


def test_resource_summary_uses_median_peak_max_and_sample_sum():
    runs = [
        {
            "mode": "P",
            "scenario": "read",
            "resources": {
                "samples": 3,
                "failed_samples": 0,
                "db_cpu_percent_one_core_median": value,
                "db_cpu_percent_one_core_peak": peak,
            },
        }
        for value, peak in ((10, 25), (30, 50), (90, 100))
    ]
    (result,) = load("build_context").resource_rows(runs, "fixture")
    assert result["db_cpu_percent_one_core_median"] == 30
    assert result["db_cpu_percent_one_core_peak"] == 100
    assert result["samples"] == 9 and result["failed_samples"] == 0


def test_derivation_is_repeatable_and_does_not_need_services(tmp_path):
    builder = load("build_context")
    for chapter in HERE.glob("[0-9][0-9]_*.md"):
        shutil.copy2(chapter, tmp_path / chapter.name)
    first = builder.build(ROOT, tmp_path)
    snapshot = (tmp_path / "evidence_snapshot.json").read_bytes()
    source_manifest = (tmp_path / "source_manifest.json").read_bytes()
    second = builder.build(ROOT, tmp_path)
    assert first == second
    assert snapshot == (tmp_path / "evidence_snapshot.json").read_bytes()
    assert source_manifest == (tmp_path / "source_manifest.json").read_bytes()
    assert first["source_files"] >= 80
