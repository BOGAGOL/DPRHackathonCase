from scanner.model import Table
from scanner.relations import memory_k, quasi_combinations, relationships
from scanner.reporting import analyze


def test_expected_relationships(synthetic, config, environment):
    inventory, _, rels = analyze([synthetic], config, environment)
    pairs = {(r["source"], r["column"]) for r in rels["derived_from"]}
    assert {("nama", c) for c in ("nama_lengkap", "nama_tanpa_gelar", "nama_rekening", "pengguna", "email")} <= pairs
    assert ("tempat_lahir", "alamat_daerah") in pairs
    dependencies = rels["dependencies"]
    assert any(r["kind"] == "arithmetic_offset" and r["source"] == "jumlah_tanggungan"
               and r["target"] == "jumlah_jiwa" and r["offset"] == "1" for r in dependencies)
    assert any(r["kind"] == "presence_iff_category" and r["source"] == "status_kawin"
               and r["target"] == "tanggal_pernikahan" and r["ratio"] == 1 for r in dependencies)
    assert next(r for r in inventory if r["column"] == "nama_lengkap")["recommendation"] == "review_minimization"


def test_k_known_answer():
    table = Table("fixture", ["a", "b", "c"], ["text"] * 3,
                  [("X", "Y", "L"), ("X", "Y", "L"), ("X", "Z", "P"), ("W", "Z", "L")], 4)
    results = memory_k(table, [(0,), (0, 1, 2)])
    assert results[0]["unique_rows"] == 1
    assert results[0]["k_min"] == 1
    assert results[1]["unique_rows"] == 2
    assert results[1]["groups"] == 3


def test_quasi_search_includes_expected(synthetic, config, environment):
    _, features, _ = analyze([synthetic], config, environment)
    combos = quasi_combinations(synthetic, features, config)
    assert tuple(sorted(synthetic.columns.index(c) for c in ("tempat_lahir", "tanggal_lahir", "jenis_kelamin"))) in [tuple(sorted(c)) for c in combos]
    assert len(combos) <= config["max_combinations"]


def test_join_numeric_values(config, environment):
    tables = [Table("a", ["code"], ["text"], [("3878912",), ("3892314",), ("3982123",)], 3),
              Table("b", ["ref"], ["text"], [("3878912",), ("3892314",), ("3982123",)], 3)]
    inventory, _, rels = analyze(tables, config, environment)
    assert len(rels["join_candidates"]) == 1
    assert rels["join_candidates"][0]["overlap_ratio"] == 1
