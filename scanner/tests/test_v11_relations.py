from scanner.model import Table
from scanner.relations import PROTECTION_NOTE
from scanner.reporting import analyze


def test_near_unique_nonnull_source_not_functional(config, environment):
    # 20 non-NULL observations out of 40; 19 distinct -> 95%, not 19/40.
    dates = [f"2000-06-{i + 1:02d}" for i in range(19)] + ["2000-06-01"]
    rows = [(value, "category") for value in dates] + [(None, "category")] * 20
    table = Table("fixture", ["tanggal_pernikahan", "target"], ["date", "text"], rows, 40)
    _, _, rels = analyze([table], config, environment)
    assert not any(r["kind"] == "functional" and r["source"] == "tanggal_pernikahan" for r in rels["dependencies"])
    near = [r for r in rels["near_unique_quasi_identifiers"] if r["column"] == "tanggal_pernikahan"]
    assert len(near) == 1
    assert near[0]["unique_ratio"] == 0.95
    assert near[0]["nonnull_rows"] == 20
    assert near[0]["unique_values"] == 19


def test_functional_source_at_ninety_percent_kept(config, environment):
    rows = [(f"source-{i}", "X") for i in range(18)] + [("source-0", "X")] * 2
    table = Table("fixture", ["source", "target"], ["text"] * 2, rows, len(rows))
    _, _, rels = analyze([table], config, environment)
    assert any(r["kind"] == "functional" and r["source"] == "source" for r in rels["dependencies"])
    assert not any(r["column"] == "source" for r in rels["near_unique_quasi_identifiers"])


def test_every_derived_column_reviews_consistent_protection(synthetic, config, environment):
    inventory, _, rels = analyze([synthetic], config, environment)
    by = {r["column"]: r for r in inventory}
    for relation in rels["derived_from"]:
        target = by[relation["column"]]
        assert target["recommendation"] == "review_minimization"
        assert relation["source"] in target["consistent_protection_with"].split(";")
        assert target["consistent_protection_with"] == target["derived_from"]
        assert target["reason"].count(PROTECTION_NOTE) == 1
    assert "nama" in by["email"]["consistent_protection_with"].split(";")
    assert "delete" not in {r["recommendation"] for r in inventory}
    assert rels["near_unique_quasi_identifiers"]


def test_password_hash_survives_minimization_review(config, environment):
    values = [f"Rekaan {chr(65 + i)}ra" for i in range(24)]
    table = Table("fixture", ["nama", "password"], ["text"] * 2, [(v, v) for v in values], len(values))
    inventory, _, _ = analyze([table], config, environment)
    password = next(r for r in inventory if r["column"] == "password")
    assert password["recommendation"] == "hash"
    assert password["consistent_protection_with"] == "nama"
    assert PROTECTION_NOTE in password["reason"]


def test_equal_normalized_username_does_not_become_source_of_person_name(synthetic, config, environment):
    inventory, _, rels = analyze([synthetic], config, environment)
    assert not any(r["source"] == "pengguna" and r["column"] in {"nama", "nama_lengkap", "nama_tanpa_gelar"}
                   for r in rels["derived_from"])
    by = {r["column"]: r for r in inventory}
    assert "pengguna" not in by["nama_lengkap"]["consistent_protection_with"].split(";")
