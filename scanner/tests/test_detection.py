import pytest

from scanner.detection import PATTERNS, classify, embedded_findings, features, valid_nik
from scanner.model import Table
from scanner.reporting import analyze


@pytest.mark.parametrize("kind,value", [
    ("email", "rekaan@fixture.example"), ("telepon", "081234569700"),
    ("telepon", "021-7234567"), ("telepon", "+6281234569700"),
    ("nik", "3174010101909700"), ("npwp", "12.345.678.9-012.345"),
    ("tanggal", "2000-01-03"), ("alamat", "Jl. Imajinasi No. 12"),
])
def test_patterns(kind, value):
    assert PATTERNS[kind].search(value)


def test_features_and_negative_evidence():
    f = features(["47839210569700", "47839210569701", None])
    assert f["regex_ratios"]["nik"] == 0
    assert f["digit_ratio"] == 1
    assert f["fixed_length_ratio"] == 1
    assert f["unique_ratio"] == 1
    assert f["null_ratio"] == pytest.approx(1 / 3)
    assert not valid_nik("1111111111111111")


def test_names_alone_do_not_auto_accept(config, environment):
    result, _ = classify("no_ktp", ["<ciphertext>"] * 5, config, environment)
    assert result["triage"] == "needs_review"
    assert result["content_score"] < 60
    result, _ = classify("email", [None] * 5, config, environment)
    assert result["triage"] == "needs_review"


def test_disguised_names(synthetic, config, environment):
    disguised = Table(synthetic.name, [f"col_{i+1:02d}" for i in range(len(synthetic.columns))],
                      synthetic.data_types, synthetic.rows, synthetic.total)
    inventory, _, rels = analyze([disguised], config, environment)
    found = dict(zip(synthetic.columns, inventory))
    for col, kind in [("email", "email"), ("handphone", "telepon"), ("no_ktp", "identifier_lain"),
                      ("rekening", "rekening"), ("tanggal_lahir", "tanggal_lahir"), ("alamat_daerah", "alamat")]:
        assert found[col]["detected_type"] == kind, (col, found[col])
        assert found[col]["confidence"] >= 60
        assert found[col]["name_score"] == 0
    assert any(r["source"] == "col_01" and r["column"] == "col_02" for r in rels["derived_from"])


def test_misleading_regex(synthetic, config, environment):
    inventory, f, _ = analyze([synthetic], config, environment)
    by = {r["column"]: r for r in inventory}
    assert f[(synthetic.name, "rekening")]["regex_ratios"]["nik"] == 1
    assert by["rekening"]["detected_type"] == "rekening"
    assert by["rekening"]["pdp_class"] == "spesifik"
    assert by["no_ktp"]["detected_type"] == "nik"
    assert by["no_ktp"]["triage"] == "needs_review"
    baseline, _, _ = analyze([synthetic], config, environment, baseline=True)
    assert next(r for r in baseline if r["column"] == "rekening")["detected_type"] == "nik"


def test_priority_and_religion(synthetic, config, environment):
    inventory, _, _ = analyze([synthetic], config, environment)
    for row in inventory:
        assert row["priority_score"] == sum(row["f_" + k] for k in ("sensitivity", "volume", "exposure", "exploitability", "impact", "recovery"))
        assert 6 <= row["priority_score"] <= 30
    religion = next(r for r in inventory if r["column"] == "agama")
    assert religion["pdp_class"] == "umum"
    assert "rawan diskriminasi" in religion["reason"]


def test_embedded():
    found = embedded_findings("Hubungi rekaan@fixture.example atau 081234569700; rek 9876543210123456")
    assert {"email", "telepon", "rekening"} <= {kind for kind, _ in found}


def test_sensitive_context_not_downgraded_by_generic_shape(config, environment):
    result, _ = classify("biometrik", ["47839210569700", "47839210569701"], config, environment)
    assert result["pdp_class"] == "spesifik"
    assert result["triage"] == "needs_review"


@pytest.mark.parametrize("values", [["rahasia rekaan", "sandi rekaan"], ["$argon2id$v=19$rekaan$synthetic"]])
def test_password_always_hash(values, config, environment):
    result, _ = classify("password", values, config, environment)
    assert result["recommendation"] == "hash"
    assert "Argon2id" in result["reason"]
    baseline, _ = classify("password", values, config, environment, baseline=True)
    assert baseline["recommendation"] == "hash"
