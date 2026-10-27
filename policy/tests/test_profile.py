import csv
import json
from pathlib import Path

import pytest
import yaml

from policy import build_profile as builder
from infra.protected.apply import load_profile


ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "evidence/scanner/before_v1/inventory.csv"
OVERRIDES = ROOT / "policy/overrides.yaml"
CONTRACT = ROOT / "docs/contracts/CONTRACT.md"


def test_assessment_and_overrides_match_every_contract_column_without_samples():
    profile = builder.build(INVENTORY,OVERRIDES,CONTRACT)
    fields = profile["columns"]
    assert len(fields)==29 and sum(field["aead"] for field in fields.values())==25
    assert {name for name,field in fields.items() if field["bidx"]}=={"no_ktp","email","pengguna"}
    assert fields["kode_bank"]["domain"]=="FIN" and fields["nama_kppn"]["domain"] is None
    assert fields["nama_lengkap"]["assessment"]["minimization_candidate"] and fields["nama_lengkap"]["aead"]
    assert fields["tanggal_lahir"]["analyst_projection"]=="age_band"
    assert profile["derived"]["age_band"]["reference_date"]=="2026-10-01"
    assert "sample_masked" not in json.dumps(profile) and "content_score" not in json.dumps(profile)
    assert load_profile(ROOT/"policy/protection_profile.yaml")==profile


def test_inventory_changes_affect_assessment_not_binding_protection_decision(tmp_path):
    rows=list(csv.DictReader(INVENTORY.open(encoding="utf-8-sig",newline="")))
    rows[1]["confidence"]="91"
    path=tmp_path/"inventory.csv"
    with path.open("w",newline="",encoding="utf-8") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    profile=builder.build(path,OVERRIDES,CONTRACT)
    assert profile["columns"]["nama"]["assessment"]["confidence"]==91
    assert profile["columns"]["nama"]["aead"]
    assert profile["provenance"]["inventory_sha256"]!=builder.build(INVENTORY,OVERRIDES,CONTRACT)["provenance"]["inventory_sha256"]
    rows.pop()
    with path.open("w",newline="",encoding="utf-8") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    with pytest.raises(ValueError):
        builder.build(path,OVERRIDES,CONTRACT)


@pytest.mark.parametrize("change", ["plaintext_finance","extra_bidx","normalization","delete_column","bool_type"])
def test_overrides_cannot_silently_change_v1_contract(tmp_path,change):
    decisions=yaml.safe_load(OVERRIDES.read_text(encoding="utf-8"))
    if change=="plaintext_finance": decisions["columns"]["kode_bank"]["aead"]=False
    elif change=="extra_bidx": decisions["columns"]["rekening"]["bidx"]=True
    elif change=="normalization": decisions["columns"]["email"]["normalization"]="casefold"
    elif change=="delete_column": decisions["columns"].pop("nama_lengkap")
    else: decisions["columns"]["nama"]["aead"]=1
    path=tmp_path/"overrides.yaml";path.write_text(yaml.safe_dump(decisions))
    with pytest.raises(ValueError): builder.build(INVENTORY,path,CONTRACT)


def test_scores_and_unknown_recommendations_fail_closed():
    row=next(csv.DictReader(INVENTORY.open(encoding="utf-8-sig",newline="")))
    for change in ({"confidence":"NaN"},{"priority_score":"-1"},{"recommendation":"export_plaintext"},{"risk_level":"unknown"}):
        with pytest.raises(ValueError): builder.assessment({**row,**change})


def test_cli_builds_deterministically_and_records_failure(tmp_path,monkeypatch):
    monkeypatch.setattr(builder,"ROOT",tmp_path)
    output=tmp_path/"profile.yaml"
    monkeypatch.setattr("sys.argv",["build-profile","--inventory",str(INVENTORY),"--overrides",str(OVERRIDES),"--contract",str(CONTRACT),"--output",str(output)])
    builder.main();first=output.read_bytes();builder.main()
    assert output.read_bytes()==first
    report=json.loads((tmp_path/"evidence/policy/build-profile.json").read_text())
    assert report["passed"] and report["aead_columns"]==25
    monkeypatch.setattr("sys.argv",["build-profile","--inventory",str(tmp_path/"missing")])
    with pytest.raises(SystemExit): builder.main()
    assert not json.loads((tmp_path/"evidence/policy/build-profile.json").read_text())["passed"]
