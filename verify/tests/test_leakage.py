from datetime import date
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from datagen.model import COLUMNS, checksum
from verify import artifacts, artifact_scanner, known_values, leak_sim, leakage_budget, profile, residual


@pytest.fixture
def rows():
    # Entirely hand-built synthetic fixtures; never copied from organizer dump.
    result = []
    for identifier in (1, 2, 735):
        row = {c: f"fixture-{c}-{identifier}" for c in COLUMNS}
        row.update(id=identifier, tanggal_lahir=date(1986, 10, 2), tanggal_pernikahan=None,
                   jenis_kelamin="L", pekerjaan_terakhir="fixture occupation", nama_kppn="fixture office",
                   nama_bank="fixture institution", tempat_lahir="fixture town", jumlah_anak=0,
                   jumlah_tanggungan=0, jumlah_jiwa=1, no_ktp=f"00{identifier:012}")
        result.append(row)
    result[1]["tanggal_pernikahan"] = date(2010, 1, 1)
    return result


@pytest.fixture
def ledger(monkeypatch, tmp_path, rows):
    private = tmp_path / "private"
    private.mkdir()
    monkeypatch.setenv("DPR_PRIVATE_DIR", str(private))
    path = private / "known.sqlite"
    known_values.export_rows(path, rows, checksum(rows))
    known = known_values.KnownValues(path)
    yield known
    known.close()


def text_rows(rows):
    return [{c: None if row[c] is None else str(row[c]) for c in COLUMNS} for row in rows]


def test_known_normalization_and_random_key_hmac(rows, ledger):
    assert known_values.normalized(rows[0])[8].startswith("00")
    assert len(ledger.fingerprints()) == 3
    assert known_values.row_mac(b"test-key-only", ["0", None]) != known_values.row_mac(b"test-key-only", ["0", "None"])
    assert ledger.lookup([1])[1] == known_values.normalized(rows[0])
    assert ledger.lookup([]) == {}
    with pytest.raises(Exception):
        ledger.connection.execute("DELETE FROM known")
    assert ledger.connection.execute("PRAGMA temp_store").fetchone()[0] == 2


def test_exact_matching_and_missing_rows_are_not_zero_exposure(ledger, rows):
    observed = MagicMock()
    result = leak_sim.compare_rows(ledger, iter(text_rows(rows)), observed)
    assert result["status"] == "PASSED" and result["rows_checked"] == 3
    assert result["matching_counts"]["full_row_hmac_matches"] == 3
    assert result["populations"]["source_734"]["rows"] == 2
    assert result["populations"]["synthetic"]["direct_exposed_rows"] == 1
    assert observed.call_count == 3
    partial = leak_sim.compare_rows(ledger, iter(text_rows(rows[:1])))
    assert partial["status"] == "PARTIAL" and partial["missing_or_changed_full_row_fingerprints"] == 2
    with pytest.raises(ValueError, match="Duplicate"):
        leak_sim.compare_rows(ledger, iter(text_rows([rows[0], rows[0]])))


def test_batched_fallback_exact_cells_and_unknown_rows(ledger, rows):
    artifact = text_rows(rows)
    artifact[0]["nama"] = "changed-only-in-artifact"
    artifact[1]["id"] = "999"
    result = leak_sim.compare_rows(ledger, artifact)
    assert result["status"] == "PARTIAL"
    assert result["matching_counts"]["fallback_rows"] == 2
    assert result["matching_counts"]["unknown_rows"] == 1
    assert result["populations"]["all"]["exposed_cells"]["nama"] == 1
    assert result["populations"]["all"]["exposed_cells"]["no_ktp"] == 2
    assert "changed-only" not in json.dumps(result)


def test_equality_histogram_and_budget(ledger, rows):
    hist = {r["column"]: r for r in ledger.equality()}
    assert hist["no_ktp"]["equality_classes"] == 3
    assert hist["no_ktp"]["frequency_histogram"] == [{"class_size": 1, "number_of_classes": 3}]
    assert hist["tanggal_pernikahan"]["non_null_cells"] == 1
    assert hist["jenis_kelamin"]["largest_class"] == 3
    leak = leak_sim.compare_rows(ledger, text_rows(rows))
    leak.update(code_commit="fixture", worktree_code_sha256={}, targets_commit="fixture", artifact_sha256="fixture",
                known_values_baseline_checksum_sha256=checksum(rows))
    agg = residual.BeforeAggregation()
    for row in text_rows(rows):
        agg.add(row)
    report = leakage_budget.build_report(ledger, leak, agg.results())
    assert report["populations"]["all"]["ESCE"]["ratio"] == 1
    assert report["populations"]["all"]["DIE"]["ratio"] == 1
    assert report["ELS"]["bidx_count"] == 0
    assert "fixture town" not in json.dumps(report)
    summary = leakage_budget.summary_rows(report, agg.results())
    assert len(summary) == 14 and all(r["after"] == "BELUM DIUJI" for r in summary)
    assert leakage_budget.ratio(0, 0)["ratio"] is None
    leak["full_artifact_equals_known_baseline"] = False
    with pytest.raises(ValueError):
        leakage_budget.build_report(ledger, leak, agg.results())


def test_fixed_age_band_and_full_counter_projection(rows):
    assert residual.age_band("1986-10-02") == "30-39"
    assert residual.age_band("1986-10-01") == "40-49"
    assert residual.age_band(None) is None
    assert residual.age_band("2000-02-29") == "20-29"
    with pytest.raises(ValueError):
        residual.age_band("2026-10-02")
    with pytest.raises(ValueError):
        residual.age_band("invalid")
    aggregate = residual.BeforeAggregation()
    for row in text_rows(rows):
        aggregate.add(row)
    report = aggregate.results()
    assert len(report["attributes"]) == 6 and "is_null_tanggal_pernikahan" in report["attributes"]
    assert len(report["populations"]["all"]["combinations"]) == 41
    assert report["populations"]["all"]["birth_reference"]["k_min"] == 3
    assert report["populations"]["source_734"]["birth_reference"]["k_min"] == 2
    assert len(report["omitted_constant_null_indicators"]) == 24
    assert "fixture town" not in json.dumps(report)
    assert residual.group_metrics({}, ["x"])["unique_ratio"] is None


def test_copy_decoding_reordered_columns_null_and_escapes(tmp_path, rows):
    columns = list(reversed(COLUMNS))
    values = text_rows(rows[:1])[0]
    values["nama"] = "fixture\tvalue\\literal\nline"
    encoded = []
    for col in columns:
        v = values[col]
        encoded.append(r"\N" if v is None else v.replace("\\", "\\\\").replace("\t", r"\t").replace("\n", r"\n"))
    text = "COPY public.anggota (" + ", ".join(columns) + ") FROM stdin;\n" + "\t".join(encoded) + "\n\\.\n"
    path = tmp_path / "fixture.sql"
    path.write_text(text, encoding="utf-8")
    assert list(artifacts.copy_rows(path)) == [values]
    path.write_text(text.replace("\\.\n", ""))
    with pytest.raises(ValueError, match="Truncated"):
        list(artifacts.copy_rows(path))


@pytest.mark.parametrize("text", ["COPY public.other (id) FROM stdin;\n", "COPY public.anggota (id) FROM stdin;\n", "INSERT INTO public.anggota VALUES (1);\n", "-- empty\n"])
def test_reject_unsupported_or_empty_sql(tmp_path, text):
    path = tmp_path / "bad.sql"
    path.write_text(text)
    with pytest.raises(ValueError):
        list(artifacts.copy_rows(path))


def test_private_path_and_snapshot_expansion(monkeypatch, tmp_path):
    monkeypatch.setenv("DPR_PRIVATE_DIR", str(tmp_path / "private"))
    (tmp_path / "private").mkdir()
    artifact = tmp_path / "private" / "fixture.dump"
    artifact.write_bytes(b"PGDMPfixture")
    out = tmp_path / "private" / "expanded.sql"
    process = MagicMock(return_value=MagicMock(returncode=0))
    monkeypatch.setattr(artifacts.subprocess, "run", process)
    assert artifacts.expand_dump(artifact, out) == out
    command = process.call_args.args[0]
    assert "--file=-" in command and not any("--dbname" in p for p in command)
    with pytest.raises(FileExistsError):
        artifacts.expand_dump(artifact, out)
    with pytest.raises(ValueError):
        artifacts.private_path(tmp_path / "outside")
    artifact.write_bytes(b"bad")
    with pytest.raises(ValueError):
        artifacts.expand_dump(artifact, out)
    monkeypatch.delenv("DPR_PRIVATE_DIR")
    with pytest.raises(ValueError):
        artifacts.private_path(out)


def test_export_failure_guard_and_database_read_only(monkeypatch, tmp_path, rows):
    monkeypatch.setenv("DPR_PRIVATE_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="checksum"):
        known_values.export_rows(tmp_path / "bad.sqlite", rows, "different")
    with pytest.raises(FileExistsError):
        known_values.export_rows(tmp_path / "bad.sqlite", rows, checksum(rows))
    conn, cursor = MagicMock(), MagicMock()
    conn.__enter__.return_value = conn
    conn.cursor.return_value.__enter__.return_value = cursor
    cursor.__iter__.return_value = iter(rows)
    monkeypatch.setattr(known_values, "parameters", lambda *a: {})
    monkeypatch.setattr(known_values.psycopg, "connect", lambda **k: conn)
    meta = known_values.export_database(tmp_path / "valid.sqlite", "baseline_1m", checksum(rows))
    assert meta["rows"] == 3 and cursor.itersize == 10000
    assert "READ ONLY" in conn.execute.call_args.args[0]


def test_profile_waits_and_reads_real_module_a_shape(tmp_path):
    absent = tmp_path / "missing.yaml"
    assert len(profile.protection_plan("baseline_dump", absent)["sensitive"]) == 25
    with pytest.raises(profile.PendingProtection):
        profile.protection_plan("protected_dump_no_key", absent)
    assert all(r["status"] == "BELUM DIUJI" for r in leak_sim.pending_scenarios(absent))
    data = {"profile_version": 1, "protection_version": 1, "null_policy": "preserve_null", "columns": {}}
    for c in COLUMNS[1:]:
        data["columns"][c] = {"domain": "FIN" if c in profile.FIN else "PII" if c in profile.PII else None,
                               "aead": c in profile.SENSITIVE, "storage_column": c + "_ct" if c in profile.SENSITIVE else c,
                               "bidx": c in ("no_ktp", "email", "pengguna"), "bidx_column": c + "_bidx"}
    path = tmp_path / "profile.yaml"
    path.write_text(yaml.safe_dump(data))
    plan = profile.protection_plan("protected_dump_with_finance_key", path)
    assert plan["authorized_decrypt_domain"] == "FIN" and plan["requires_decryption_hook"]
    assert len(plan["bidx"]) == 3
    assert len(leak_sim.pending_scenarios(path)) == 5
    data["columns"]["kode_bank"]["aead"] = False
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError):
        profile.protection_plan("protected_dump_no_key", path)


def test_artifact_scanner_same_input_no_source_values(tmp_path, rows):
    agg = residual.BeforeAggregation()
    for row in text_rows(rows):
        agg.add(row)
    artifact_scanner.scan_reservoir([tuple(row[c] for c in COLUMNS) for row in rows], 3, "fixture-sha",
                                    agg.results()["populations"]["all"]["combinations"], .1, tmp_path)
    meta = json.loads((tmp_path / "run_meta.json").read_text())
    assert meta["source"]["artifact_sha256"] == "fixture-sha"
    assert meta["scanner_version"] == "1.2.0" and meta["method"] == "combined"
    assert len(list(tmp_path.glob("*"))) == 6


def test_pipeline_and_budget_cli(monkeypatch, tmp_path, ledger, rows):
    # Exercise orchestration with tiny independent fixtures and mocked I/O guards.
    evidence = tmp_path / "evidence/datasets"
    evidence.mkdir(parents=True)
    artifact = tmp_path / "private" / "fixture.dump"
    artifact.write_bytes(b"PGDMPfixture")
    dataset = {"baseline_checksum_sha256": checksum(rows), "snapshot": {"sha256": leak_sim.file_hash(artifact)}, "targets_commit": "fixture"}
    (evidence / "baseline_1m.json").write_text(json.dumps(dataset))
    monkeypatch.setattr(leak_sim, "ROOT", tmp_path)
    monkeypatch.setattr(leak_sim, "require_disk_space", lambda **k: 10**11)
    monkeypatch.setattr(leak_sim, "KnownValues", lambda path: ledger)
    ledger.meta["rows"] = 1000000
    monkeypatch.setattr(leak_sim, "expand_dump", lambda *a: None)
    monkeypatch.setattr(leak_sim, "copy_rows", lambda *a: iter(text_rows(rows)))
    # A deliberately incomplete artifact must fail before complete-budget claims.
    with pytest.raises(ValueError, match="Partial"):
        leak_sim.run(artifact, Path(ledger.connection.execute("PRAGMA database_list").fetchone()[2]))
    assert json.loads((tmp_path / "evidence/leak/baseline_dump.json").read_text())["status"] == "PARTIAL"


def test_cli_pending_is_machine_evidence_and_hides_private_values(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(leak_sim, "ROOT", tmp_path)
    monkeypatch.setattr("sys.argv", ["verify.leak_sim", "--artifact", "unused", "--known-values", "unused",
                                    "--scenario", "protected_dump_no_key"])
    monkeypatch.setattr(leak_sim, "run", lambda *a, **k: (_ for _ in ()).throw(profile.PendingProtection("Waiting for profile")))
    with pytest.raises(SystemExit, match="pending"):
        leak_sim.main()
    record = json.loads((tmp_path / "evidence/leak/protected_dump_no_key.json").read_text())
    assert record["status"] == "BELUM DIUJI" and "ESCE" not in record
    monkeypatch.setattr(leak_sim, "run", lambda *a, **k: (_ for _ in ()).throw(ValueError("private-fixture-only")))
    with pytest.raises(SystemExit, match="private details withheld"):
        leak_sim.main()
    assert "private-fixture-only" not in (tmp_path / "evidence/leak/failure.json").read_text()


def test_cli_success_and_budget_rejects_other_ledger(monkeypatch, tmp_path, ledger, rows, capsys):
    monkeypatch.setattr("sys.argv", ["verify.leak_sim", "--artifact", "unused", "--known-values", "unused", "--scenario", "baseline_dump"])
    monkeypatch.setattr(leak_sim, "run", lambda *a, **k: {"status": "PASSED", "rows_checked": 3, "total_elapsed_s": .1})
    leak_sim.main()
    assert json.loads(capsys.readouterr().out)["rows"] == 3
    leak = leak_sim.compare_rows(ledger, text_rows(rows))
    leak["known_values_baseline_checksum_sha256"] = "other-dataset"
    with pytest.raises(ValueError, match="different baselines"):
        leakage_budget.build_report(ledger, leak, {})


def test_budget_cli_preserves_before_after_status(monkeypatch, tmp_path):
    for name in ("leak.json", "residual.json"):
        (tmp_path / name).write_text("{}")
    monkeypatch.setattr("sys.argv", ["verify.leakage_budget", "--known-values", "unused", "--leak", str(tmp_path / "leak.json"),
                                    "--residual", str(tmp_path / "residual.json")])
    known = MagicMock()
    monkeypatch.setattr(leakage_budget, "ROOT", tmp_path)
    monkeypatch.setattr(leakage_budget, "KnownValues", lambda *a: known)
    monkeypatch.setattr(leakage_budget, "build_report", lambda *a: {"status": "PASSED"})
    monkeypatch.setattr(leakage_budget, "summary_rows", lambda *a: [{"before": 1, "after": "BELUM DIUJI"}])
    leakage_budget.main()
    assert known.close.called
    assert "BELUM DIUJI" in (tmp_path / "evidence/leakage/before_after.csv").read_text()
