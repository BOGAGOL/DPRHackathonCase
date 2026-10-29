"""Synthetic negative tests for presentation context, never service credentials."""

import importlib.util
import json
from pathlib import Path
import shutil

import pytest

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(
        "presentation_" + name, HERE / (name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def context(tmp_path):
    target = tmp_path / "presentation"
    shutil.copytree(
        HERE, target, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache")
    )
    return target


def test_current_sources_charts_topics_and_timing():
    result = load("verify_context").validate(HERE, ROOT)
    assert result["passed"], result["errors"]
    assert (
        result["main_slides"],
        result["core_seconds"],
        result["extended_seconds_including_demo"],
        result["claims"],
    ) == (8, 300, 840, 14)


def test_missing_required_topic_is_rejected(context):
    path = context / "deck_plan.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for slide in data["slides"]:
        slide["topics"] = [t for t in slide["topics"] if t != "kinerja"]
    path.write_text(json.dumps(data), encoding="utf-8")
    result = load("verify_context").validate(context)
    assert any(
        e["kind"] == "slide_or_required_topic_coverage" for e in result["errors"]
    )


def test_demo_cannot_be_added_outside_total_budget(context):
    path = context / "deck_plan.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["slides"][4]["extended_seconds"] += 240
    path.write_text(json.dumps(data), encoding="utf-8")
    result = load("verify_context").validate(context)
    assert any(e["kind"] == "timing_budget_mismatch" for e in result["errors"])


def test_target_failure_cannot_be_relabelled_as_success(context):
    path = context / "evidence_cards.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["cards"]["K10"]["data"][0]["P01_ratio_passed"] = True
    path.write_text(json.dumps(data), encoding="utf-8")
    result = load("verify_context").validate(context)
    assert any(
        e["kind"] == "performance_scope_or_target_mismatch" for e in result["errors"]
    )


def test_changed_chart_value_is_rejected(context):
    path = context / "tables/chart-db-nik.csv"
    data = path.read_text(encoding="utf-8").replace("2492.097301693016", "999999", 1)
    path.write_text(data, encoding="utf-8")
    result = load("verify_context").validate(context)
    assert any(e["kind"] == "db_chart_mismatch" for e in result["errors"])


def test_chart_cannot_silently_drop_a_scale(context):
    path = context / "tables/chart-db-nik.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[:3]) + "\n", encoding="utf-8")
    result = load("verify_context").validate(context)
    assert any(e["kind"] == "db_chart_scale_or_mode_omitted" for e in result["errors"])


def test_api_plan_cannot_silently_turn_into_results(context):
    path = context / "evidence_cards.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["cards"]["K12"]["data"]["status"] = "COMPLETED"
    path.write_text(json.dumps(data), encoding="utf-8")
    result = load("verify_context").validate(context)
    assert any(
        e["kind"] == "api_status_changed_requires_narrative_review"
        for e in result["errors"]
    )


def test_handoff_links_are_local_and_chapters_current(context):
    path = context / "01_BRIEF_DAN_ALUR.md"
    path.write_text(
        path.read_text(encoding="utf-8") + "\n[Outside](../README.md)\n",
        encoding="utf-8",
    )
    result = load("verify_context").validate(context)
    assert {e["kind"] for e in result["errors"]} >= {
        "chapter_not_consolidated",
        "missing_or_nonlocal_link",
    }


def test_improvement_calculation_and_invalid_baseline():
    builder = load("build_context")
    assert builder.improvement_percent(80, 40) == 50
    with pytest.raises(ValueError):
        builder.improvement_percent(0, 40)


def test_builder_is_repeatable_without_runtime(tmp_path):
    for chapter in HERE.glob("[0-9][0-9]_*.md"):
        shutil.copy2(chapter, tmp_path / chapter.name)
    builder = load("build_context")
    first = builder.build(ROOT, tmp_path)
    artifact = (tmp_path / "evidence_cards.json").read_bytes()
    second = builder.build(ROOT, tmp_path)
    assert (
        first == second and artifact == (tmp_path / "evidence_cards.json").read_bytes()
    )
    assert first["main_slides"] == 8 and first["claims"] == 14
