from copy import deepcopy
from pathlib import Path

import pytest

from scanner.__main__ import main
from scanner.detection import classify
from scanner.priority import load_type_policy, priority_factors, rank


@pytest.mark.parametrize("score,expected", [(6, "P3"), (12, "P3"), (13, "P2"), (18, "P2"),
                                           (19, "P1"), (24, "P1"), (25, "P0"), (30, "P0")])
def test_priority_boundaries(score, expected):
    assert rank(score) == expected


@pytest.mark.parametrize("kind,impact", [("nik", 5), ("rekening", 5), ("npwp", 5), ("kesehatan", 5),
                                        ("alamat", 4), ("telepon", 4), ("email", 4),
                                        ("tanggal_lahir", 3), ("agama", 3), ("keluarga", 3),
                                        ("nama", 2), ("kategori", 1), ("operasional", 1)])
def test_type_factors_loaded_from_yaml(kind, impact, environment):
    factors = priority_factors(kind, 90, 1, {**environment, "impact": 1}, load_type_policy())
    assert factors["impact"] == impact  # legacy environment impact cannot override type policy
    assert factors["sensitivity"] == impact
    assert {k: factors[k] for k in environment} == environment


def test_custom_type_policy_changes_both_auditable_factors(config, environment):
    custom = deepcopy(config)
    custom["type_policy"]["types"]["email"] = {"sensitivity": 1, "impact": 2}
    row, _ = classify("email", ["rekaan@fixture.example"], custom, environment)
    assert row["f_sensitivity"] == 1
    assert row["f_impact"] == 2
    assert row["priority_score"] == sum(row["f_" + k] for k in ("sensitivity", "volume", "exposure", "exploitability", "impact", "recovery"))


def test_spread_across_environments_does_not_fake_p3(environment):
    policy = load_type_policy()
    before = [rank(sum(priority_factors(kind, content, 1, environment, policy).values()))
              for kind, content in [("nik", 95), ("keluarga", 75), ("nama", 10), ("operasional", 95)]]
    assert set(before) == {"P0", "P1", "P2"}
    after = {"volume": 3, "exposure": 2, "recovery": 3}
    assert rank(sum(priority_factors("operasional", 95, 1, after, policy).values())) == "P3"
    assert sum(environment.values()) + 3 == 16  # minimum before score under six-factor rule


@pytest.mark.parametrize("text", ["default: {sensitivity: 0, impact: 1}\ntypes: {}",
                                  "default: {sensitivity: 1, impact: 6}\ntypes: {}",
                                  "default: {sensitivity: true, impact: 1}\ntypes: {}",
                                  "default: {impact: 1}\ntypes: {}", "[]"])
def test_bad_type_policy_rejected(text, tmp_path):
    path = tmp_path / "impact.yaml"
    path.write_text(text)
    with pytest.raises(ValueError):
        load_type_policy(path)


def test_cli_uses_custom_policy_and_legacy_environment(sql_dump, tmp_path):
    import csv
    import json
    impact, environment, out = tmp_path / "impact.yaml", tmp_path / "legacy.yaml", tmp_path / "out"
    impact.write_text("default: {sensitivity: 1, impact: 1}\ntypes: {email: {sensitivity: 2, impact: 3}}")
    environment.write_text("volume: 3\nexposure: 5\nrecovery: 5\nimpact: 5")
    assert main(["dump", "--file", str(sql_dump), "--out", str(out), "--impact", str(impact),
                 "--environment", str(environment)]) == 0
    with (out / "inventory.csv").open(encoding="utf-8") as handle:
        email = next(r for r in csv.DictReader(handle) if r["column"] == "email")
    assert email["f_impact"] == "3"
    assert email["f_sensitivity"] == "2"
    meta = json.loads((out / "run_meta.json").read_text())
    assert meta["source"]["legacy_environment_impact_ignored"]
    assert set(meta["source"]["environment_factors"]) == {"volume", "exposure", "recovery"}


def test_cli_rejects_invalid_impact(sql_dump, tmp_path, capsys):
    path = tmp_path / "impact.yaml"
    path.write_text("default: {sensitivity: 9, impact: 1}\ntypes: {}")
    assert main(["dump", "--file", str(sql_dump), "--out", str(tmp_path / "out"), "--impact", str(path)]) == 2
    assert "impact.yaml" in capsys.readouterr().err
