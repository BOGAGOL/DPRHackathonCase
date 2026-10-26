import csv
import json
from pathlib import Path

import pytest

from scanner.__main__ import main
from scanner.model import INVENTORY_FIELDS


def test_dump_cli_no_leak(sql_dump, synthetic, tmp_path, capsys):
    out = tmp_path / "output"
    assert main(["dump", "--file", str(sql_dump), "--out", str(out)]) == 0
    expected = {"inventory.csv", "relations.json", "k_anonymity.json", "run_meta.json", "report.html", "features.json"}
    assert expected <= {p.name for p in out.iterdir()}
    emitted = "\n".join(p.read_text(encoding="utf-8") for p in out.iterdir()) + capsys.readouterr().out
    for row in synthetic.rows:
        for value in row:
            if value is not None and len(str(value)) >= 6:
                assert str(value) not in emitted, "Output contains a complete fixture value"
    with (out / "inventory.csv").open(encoding="utf-8", newline="") as handle:
        assert csv.DictReader(handle).fieldnames == INVENTORY_FIELDS
    meta = json.loads((out / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["review_state"] == "raw_before_human_review"
    assert meta["table_counts"]["public.fixture"]["total_rows"] == 24
    assert "password" not in meta["source"]


def test_baseline_cli(sql_dump, tmp_path):
    out = tmp_path / "baseline"
    assert main(["dump", "--file", str(sql_dump), "--out", str(out), "--baseline", "regex_only"]) == 0
    assert json.loads((out / "run_meta.json").read_text())["method"] == "regex_only"


def test_file_cli_no_leak(tmp_path):
    path = tmp_path / "demo.log"
    pii = ["imajinasi@fixture.example", "081234569700", "9876543210123456"]
    path.write_text("Hubungi " + " atau ".join(pii), encoding="utf-8")
    out = tmp_path / "files-out"
    assert main(["files", "--file", str(path), "--out", str(out)]) == 0
    emitted = "\n".join(p.read_text(encoding="utf-8") for p in out.iterdir())
    assert all(value not in emitted for value in pii)
    with (out / "findings.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert {"email", "telepon", "rekening"} <= {r["detected_type"] for r in rows}
    assert all(r["line"] == "1" for r in rows)


def test_files_limit_and_directory_excludes_output(tmp_path):
    path = tmp_path / "many.log"
    path.write_text("Hubungi rekaan@fixture.example\n" * 30, encoding="utf-8")
    out = tmp_path / "generated"
    assert main(["files", str(tmp_path), "--sample", "2", "--out", str(out)]) == 0
    assert main(["files", str(tmp_path), "--sample", "2", "--out", str(out)]) == 0
    meta = json.loads((out / "run_meta.json").read_text())
    assert meta["source"]["total_matches"] == 30
    assert meta["source"]["exported_matches"] == 2
    assert len(meta["source"]["paths"]) == 1


def test_after_environment(sql_dump, tmp_path):
    out = tmp_path / "after"
    assert main(["dump", "--file", str(sql_dump), "--label", "after", "--out", str(out)]) == 0
    with (out / "inventory.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert all(r["f_exposure"] == "2" and r["f_recovery"] == "3" for r in rows)


def test_errors_do_not_print_secrets(tmp_path, monkeypatch, capsys):
    secret = "never-print-this-secret"
    def fail_connect(*args, **kwargs):
        raise RuntimeError(secret)
    monkeypatch.setattr("scanner.sources.psycopg.connect", fail_connect)
    monkeypatch.setenv("SCANNER_DATABASE_URL", "postgresql://scanner_user:" + secret + "@127.0.0.1:1/postgres")
    assert main(["db", "--out", str(tmp_path / "out")]) == 2
    captured = capsys.readouterr()
    assert secret not in captured.out + captured.err
    assert "Traceback" not in captured.err
    monkeypatch.delenv("SCANNER_DATABASE_URL")
    assert main(["db", "--out", str(tmp_path / "out")]) == 2
    assert "SCANNER_DATABASE_URL" in capsys.readouterr().err


def test_custom_label_needs_environment(sql_dump, tmp_path, capsys):
    out = tmp_path / "out"
    assert main(["dump", "--file", str(sql_dump), "--out", str(out), "--label", "custom"]) == 2
    assert "--environment" in capsys.readouterr().err
    assert not out.exists()


def test_bad_dump_does_not_echo_rows(tmp_path, capsys):
    path = tmp_path / "bad.sql"
    path.write_text("CREATE TABLE demo (a text); INSERT INTO demo VALUES (SECRET_PRIVATE_DATA());")
    assert main(["dump", "--file", str(path), "--out", str(tmp_path / "out")]) == 2
    captured = capsys.readouterr()
    assert "SECRET_PRIVATE_DATA" not in captured.out + captured.err
