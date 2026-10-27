"""Behavioral regressions for findings in the first run; all data invented."""
import pytest

from scanner.detection import classify, name_scores
from scanner.model import Table
from scanner.reporting import analyze


def identities():
    return ["4783921056" + f"{9700 + i:04d}" for i in range(24)]


@pytest.mark.parametrize("column", ["ktp", "no_ktp", "nik", "nomor_kependudukan", "noKTP", "nomorNIK"])
def test_nonstandard_nik_requires_content(column, config, environment):
    row, f = classify(column, identities(), config, environment)
    assert name_scores(column)["nik"] == 100
    assert row["detected_type"] == "nik"
    assert row["content_score"] >= 60
    assert "panjang tidak baku" in row["reason"]
    assert f["regex_ratios"]["nik"] == 0
    assert "**********" not in str(f)  # features contain aggregates, not masks/values


@pytest.mark.parametrize("values", [["ciphertext"] * 24, [None] * 24,
                                    ["47839210569700"] * 24,
                                    ["47839210569700", "478392105697011", "4783921056970122"]])
def test_nik_name_cannot_supply_missing_shape(values, config, environment):
    row, _ = classify("no_ktp", values, config, environment)
    assert row["triage"] != "auto_accept"
    assert "kandidat NIK didukung" not in row["reason"]


def test_anonymous_nonstandard_identifier_stays_review(config, environment):
    row, _ = classify("col_01", identities(), config, environment)
    assert row["detected_type"] == "identifier_lain"
    assert row["triage"] == "needs_review"


@pytest.mark.parametrize("width", [14, 15, 18])
def test_anonymous_fixed_digits_do_not_confirm_tax_or_national_identity(width, config, environment):
    values = ["047839210569".ljust(width - 2, "7") + f"{i:02d}" for i in range(24)]
    row, _ = classify("col_01", values, config, environment)
    assert (row["detected_type"], row["triage"]) == ("identifier_lain", "needs_review")


def test_bank_context_does_not_overrule_valid_named_nik(config, environment):
    values = [f"317401{i + 1:02d}0690{9700 + i:04d}" for i in range(24)]
    row, _ = classify("nik", values, config, environment, bank_context=True)
    assert row["detected_type"] == "nik"
    account, _ = classify("rekening", values, config, environment, bank_context=True)
    assert account["detected_type"] == "rekening"


@pytest.mark.parametrize("column,values", [
    ("nama_bank", ["Bank BCA", "Bank BRI", "Bank BNI"] * 30),
    ("nama_bank", ["BCA", "BRI", "BNI"] * 30),
    ("nama_kppn", ["KPPN Rekaan", "KPPN Imajinasi"] * 30),
    ("nama", ["Zafira Arunika"] * 30),
    ("col_01", ["Zafira Arunika", "Nayaka Rekaan"] * 30),
    ("nama", [f"Rekaan {chr(65+i)}ra" for i in range(20)]),
    ("nama", [f"Rekaan {chr(65+i)}ra" for i in range(21)] * 10),
])
def test_low_cardinality_is_category(column, values, config, environment):
    row, f = classify(column, values, config, environment)
    assert row["detected_type"] == "kategori"
    assert f["unique_count"] <= 20 or f["unique_ratio"] < 0.2
    assert f["type_content_scores"]["nama"] == 0


@pytest.mark.parametrize("column,values", [
    ("nama_bank", ["Bank BNI", "Bank BRI", "Bank BCA"] * 10),
    ("nama_kppn", ["KPPN Imajinasi", "KPPN Rekaan"] * 10),
])
def test_institution_category_requires_content_evidence(column, values, config, environment):
    row, f = classify(column, values, config, environment)
    assert (row["detected_type"], row["pdp_class"]) == ("kategori", "non_pribadi")
    assert f["institution_reference"]
    assert "asosiasi dengan individu" in row["reason"]
    unknown, _ = classify(column, ["Zafira Arunika", "Nayaka Rekaan"] * 10, config, environment)
    assert unknown["pdp_class"] == "umum"


def test_regex_only_does_not_use_relations_or_names(synthetic, config, environment):
    inventory, features, relations = analyze([synthetic], config, environment, baseline=True)
    assert not relations["derived_from"] and not relations["dependencies"]
    assert all(row["name_score"] == 0 and not row["derived_from"] for row in inventory)


def test_above_both_cardinality_cutoffs_can_be_person_name(config, environment):
    row, f = classify("nama", [f"Rekaan {chr(65+i)}ra" for i in range(21)], config, environment)
    assert f["unique_count"] == 21
    assert row["detected_type"] == "nama"
    assert row["recommendation"] == "retain+mask_for_analyst"
    assert "kamus" in row["reason"]


def test_marriage_date_with_conditional_nulls(synthetic, config, environment):
    inventory, f, _ = analyze([synthetic], config, environment)
    by = {r["column"]: r for r in inventory}
    assert by["tanggal_pernikahan"]["detected_type"] == "tanggal_pernikahan"
    assert by["tanggal_lahir"]["detected_type"] == "tanggal_lahir"
    assert "pola NULL bersyarat" in by["tanggal_pernikahan"]["reason"]
    assert "status_kawin" in f[(synthetic.name, "tanggal_pernikahan")]["conditional_presence"]["source_columns"]


def test_marriage_name_without_date_does_not_auto_accept(config, environment):
    row, _ = classify("tanggal_pernikahan", ["ciphertext"] * 30, config, environment)
    assert row["triage"] == "needs_review"
    assert row["content_score"] < 60


@pytest.mark.parametrize("column", ["jumlah_anak", "jumlah_tanggungan", "jumlah_jiwa"])
def test_counts_are_general_family_data(column, config, environment):
    row, f = classify(column, list(range(5)) * 20, config, environment)
    assert (row["detected_type"], row["pdp_class"], row["triage"]) == ("keluarga", "umum", "needs_review")
    assert f["family_count"]
    assert "bukan data anak individual" in row["reason"]


def test_child_personal_data_is_still_specific(config, environment):
    row, _ = classify("nama_anak", [f"Rekaan {chr(65+i)}ra" for i in range(24)], config, environment)
    assert row["pdp_class"] == "spesifik"


def test_surrogate_id_requires_sequential_integer_content(config, environment):
    row, f = classify("id", [4, 2, 1, 3], config, environment, data_type="bigint")
    assert row["detected_type"] == "operasional"
    assert row["pdp_class"] == "non_pribadi"
    assert row["recommendation"] == "retain"
    assert row["f_sensitivity"] == row["f_exploitability"] == row["f_impact"] == 1
    assert f["surrogate_id_candidate"]
    assert "kunci penghubung" in row["reason"]
    for values, dtype in [([1, 1, 2], "bigint"), ([1, 3, 5], "bigint"),
                          (["1", "2", "3"], "text"), ([None, 1, 2], "integer")]:
        invalid, features = classify("id", values, config, environment, data_type=dtype)
        assert not features["surrogate_id_candidate"]
        assert "kunci penghubung" not in invalid["reason"]


def test_birth_date_has_specific_recommendation(config, environment):
    row, _ = classify("tanggal_lahir", ["1988-06-01", "1988-06-02"], config, environment)
    assert row["recommendation"] in {"encrypt", "generalize_for_analyst"}
