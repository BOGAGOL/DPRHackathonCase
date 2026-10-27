"""Exact functional checks and structural relations, with invented values only."""
import pytest

from scanner.model import Table
from scanner.reporting import analyze


def test_source_above_eighty_percent_is_near_unique(config, environment):
    rows = [(f"invented-{i}", "category") for i in range(17)] + [("invented-0", "category")] * 3
    table = Table("fixture", ["source", "target"], ["text"] * 2, rows, len(rows))
    _, _, rels = analyze([table], config, environment)
    assert any(r["column"] == "source" and r["unique_ratio"] == .85 for r in rels["near_unique_quasi_identifiers"])
    assert not any(r["kind"] == "functional" and r["source"] == "source" for r in rels["dependencies"])


@pytest.mark.parametrize("groups", [10, 20])
def test_ninety_and_ninety_five_percent_group_consistency_are_rejected(groups, config, environment):
    rows = [(f"invented-{i}", "consistent") for i in range(groups) for _ in range(2)]
    rows[-1] = (rows[-1][0], "contradiction")
    table = Table("fixture", ["source", "target"], ["text"] * 2, rows, len(rows))
    _, _, rels = analyze([table], config, environment)
    assert not any(r["kind"] == "functional" and r["source"] == "source" and r["target"] == "target"
                   for r in rels["dependencies"])
    assert all(r["consistent_group_ratio"] == 1.0 for r in rels["dependencies"] if r["kind"] == "functional")


@pytest.mark.parametrize("matches", [True, False])
def test_city_component_is_generic_and_requires_exact_agreement(matches, config, environment):
    cities = ["KotaRekaanA", "KotaRekaanB", "KotaRekaanC"]
    rows = [(f"Jalan Imajinasi {i}, {cities[i % 3]}", cities[i % 3]) for i in range(12)]
    if not matches:
        rows[-1] = (rows[-1][0], "KotaLain")
    table = Table("fixture", ["delivery_label", "town_label"], ["text"] * 2, rows, len(rows))
    _, _, rels = analyze([table], config, environment)
    component = [r for r in rels["dependencies"] if r["kind"] == "text_component"
                 and r["source"] == "delivery_label" and r["target"] == "town_label"]
    assert bool(component) == matches
    if matches:
        assert component[0]["ratio"] == 1.0 and component[0]["compared_rows"] == 12
    assert any(r["column"] == "delivery_label" for r in rels["near_unique_quasi_identifiers"])
    assert not any(r["kind"] == "functional" and r["source"] == "delivery_label" for r in rels["dependencies"])


def test_marital_presence_relation_is_preserved(synthetic, config, environment):
    _, _, rels = analyze([synthetic], config, environment)
    assert any(r["kind"] == "presence_iff_category" and r["source"] == "status_kawin"
               and r["target"] == "tanggal_pernikahan" and r["ratio"] == 1.0 for r in rels["dependencies"])
