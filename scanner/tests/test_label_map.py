"""Evaluation contract using handmade labels and no source dataset values."""
import csv
import json

import pytest
import yaml

from scanner.__main__ import main
from scanner.evaluation import (column_key, evaluate, load_label_map, load_rows,
                                mapped_type, normalize_class, normalize_personal)
from scanner.sources import InputError

FIELDS = ["table", "column", "is_personal", "detected_type", "pdp_class", "content_score", "name_score"]


def csv_file(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def label(column, kind="email", pdp="umum", personal="yes", **extra):
    return {"table": "public.fixture", "column": column, "is_personal": personal,
            "detected_type": kind, "pdp_class": pdp, **extra}


@pytest.mark.parametrize("value,expected", [("1", True), ("0", False), ("YES", True), (" no ", False),
                                           ("true", True), ("FALSE", False), (1, True), (False, False)])
def test_normalize_personal(value, expected):
    assert normalize_personal(value) is expected


@pytest.mark.parametrize("value", ["", None, "maybe", 2])
def test_invalid_personal_is_rejected(value):
    with pytest.raises(InputError):
        normalize_personal(value)


def test_class_and_default_schema_normalization():
    assert normalize_class(" NON-PRIBADI ") == normalize_class("non_pribadi") == "non_pribadi"
    assert normalize_class("UMUM") == "umum"
    assert normalize_class("spesifik") == "spesifik"
    assert column_key(" anggota ", " field ") == column_key("public.anggota", "field")
    assert column_key("other.anggota", "Field")[1] == "Field"
    with pytest.raises(InputError):
        normalize_class("unknown")
    with pytest.raises(InputError):
        column_key("", "column")


@pytest.mark.parametrize("source,target", [
    ("PERSON_NAME", "nama"), ("NATIONAL_ID", "nik"), ("PHONE_NUMBER", "telepon"),
    ("MOBILE_PHONE", "telepon"), ("EMAIL_ADDRESS", "email"), ("PERSON_ADDRESS", "alamat"),
    ("BIRTH_DATE", "tanggal_lahir"), ("BIRTH_PLACE", "tempat_lahir"), ("RELIGION", "agama"),
    ("MARITAL_STATUS", "status_perkawinan"), ("FAMILY_CHILD_COUNT", "keluarga"),
    ("DEPENDENT_COUNT", "keluarga"), ("HOUSEHOLD_SIZE", "keluarga"),
    ("BANK_ACCOUNT_NUMBER", "rekening"), ("TAXPAYER_ID", "npwp"),
    ("BANK_ACCOUNT_HOLDER_NAME", "nama"), ("EMPLOYEE_ID", "identifier_lain"),
    ("USERNAME", "identifier_lain"), ("PERSON_LINKED_LOCATION_ID", "identifier_lain"),
    ("GENDER", "kategori"), ("OCCUPATION", "kategori"), ("GOVERNMENT_OFFICE_NAME", "kategori"),
    ("BANK_INSTITUTION_NAME", "kategori"), ("BANK_INSTITUTION_CODE", "kategori"),
    ("MARRIAGE_DATE", "tanggal_pernikahan"), ("email", "email"), (" EMAIL_ADDRESS ", "email")])
def test_taxonomy_map(source, target):
    assert mapped_type(source, load_label_map()) == target


def test_invalid_label_map_is_rejected(tmp_path):
    path = tmp_path / "map.yaml"
    path.write_text("version: 99\n")
    with pytest.raises(InputError):
        load_label_map(path)
    config = load_label_map()
    config["labels"]["INVENTED_LABEL"] = "unsupported_type"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(InputError):
        load_label_map(path)


def test_csv_headers_duplicates_and_incomplete_rows(tmp_path):
    path = tmp_path / "rows.csv"
    path.write_text("column\na\n")
    with pytest.raises(InputError):
        load_rows(path, {"table", "column"})
    csv_file(path, [label("a"), {**label("a"), "table": "fixture"}])
    with pytest.raises(InputError):
        load_rows(path, {"table", "column"})
    path.write_text("table,column\npublic.fixture\n")
    with pytest.raises(InputError):
        load_rows(path, {"table", "column"})


def test_independent_labels_and_unlabelled_id_do_not_change_denominators(tmp_path):
    truth = csv_file(tmp_path / "truth.csv", [label("a", "PERSON_NAME"),
        label("b", "BANK_INSTITUTION_NAME", "non-pribadi", "no"), label("c", "MARRIAGE_DATE")])
    rows = [label("a", "nama"), label("b", "kategori", "non_pribadi", "0"),
            label("c", "tanggal_pernikahan"), label("id", "operasional", "non_pribadi", "0")]
    rows[0]["table"] = "fixture"
    pred = csv_file(tmp_path / "pred.csv", rows)
    original = truth.read_bytes()
    result = evaluate(pred, truth)
    assert result["in_sample"] is True and result["all_labels_mapped"]
    assert result["truth_rows"] == result["evaluated_prediction_rows"] == 3
    assert result["prediction_rows"] == 4
    assert result["precision"] == result["recall"] == result["f1"] == result["f2"] == 1
    assert result["detected_type_accuracy"] == result["pdp_class_accuracy"] == 1
    assert result["unlabelled_predictions"] == [{"table": "public.fixture", "column": "id"}]
    assert truth.read_bytes() == original


def test_unmapped_labels_are_explicit_and_not_counted_as_correct(tmp_path):
    truth = csv_file(tmp_path / "truth.csv", [label("a", "UNSEEN_TYPE")])
    pred = csv_file(tmp_path / "pred.csv", [label("a", "UNSEEN_TYPE")])
    result = evaluate(pred, truth)
    assert not result["all_labels_mapped"] and len(result["unmapped_labels"]) == 2
    assert result["detected_type_accuracy"] == 0
    assert result["mismatches"][0]["fields"] == ["detected_type"]
    assert result["detected_type_confusion_matrix"] == {
        "unmapped_truth:UNSEEN_TYPE": {"unmapped_prediction:UNSEEN_TYPE": 1}}


def test_regex_only_counts_absence_as_no_detection_and_computes_f2(tmp_path):
    truth = csv_file(tmp_path / "truth.csv", [label("a", "EMAIL_ADDRESS"), label("b", "PERSON_NAME"),
        label("bank", "BANK_INSTITUTION_NAME", "non-pribadi", "0")])
    pred = csv_file(tmp_path / "pred.csv", [label("a", content_score=100, name_score=0),
        label("b", "tidak_diketahui", content_score=0, name_score=0),
        label("bank", "tidak_diketahui", content_score=0, name_score=0)])
    result = evaluate(pred, truth, baseline="regex_only")
    assert result["confusion_matrix"] == {"tp": 1, "fp": 0, "fn": 1, "tn": 1}
    assert result["precision"] == 1 and result["recall"] == 0.5
    assert result["f1"] == pytest.approx(2 / 3) and result["f2"] == pytest.approx(5 / 9)
    assert result["false_negative"] == [{"table": "public.fixture", "column": "b"}]


@pytest.mark.parametrize("score,name", [("nan", 0), ("inf", 0), (101, 0), (100, 1), ("bad", 0)])
def test_regex_only_rejects_name_scores_and_invalid_content(tmp_path, score, name):
    truth = csv_file(tmp_path / "truth.csv", [label("a")])
    pred = csv_file(tmp_path / "pred.csv", [label("a", content_score=score, name_score=name)])
    with pytest.raises(InputError):
        evaluate(pred, truth, baseline="regex_only")


def test_missing_predictions_remain_in_denominator_and_zero_division_is_safe(tmp_path):
    truth = csv_file(tmp_path / "truth.csv", [label("a")])
    pred = csv_file(tmp_path / "pred.csv", [])
    result = evaluate(pred, truth)
    assert result["precision"] == result["recall"] == result["f1"] == result["f2"] == 0
    assert len(result["missing_predictions"]) == 1
    assert result["detected_type_accuracy"] == result["pdp_class_accuracy"] == 0


def test_evaluate_cli_writes_machine_output_and_checks_metadata(tmp_path):
    truth = csv_file(tmp_path / "truth.csv", [label("a", "EMAIL_ADDRESS")])
    pred = csv_file(tmp_path / "pred.csv", [label("a", content_score=100, name_score=0)])
    meta = tmp_path / "run_meta.json"
    meta.write_text(json.dumps({"method": "regex_only", "scanner_version": "1.1.0"}))
    out = tmp_path / "evidence" / "evaluation.json"
    assert main(["evaluate", "--pred", str(pred), "--truth", str(truth), "--out", str(out),
                 "--baseline", "regex_only"]) == 0
    result = json.loads(out.read_text())
    assert result["method"] == "regex_only" and result["scanner_version"] == "1.1.0"
    assert result["f2"] == 1
    meta.write_text(json.dumps({"method": "combined"}))
    with pytest.raises(InputError):
        evaluate(pred, truth, baseline="regex_only")
