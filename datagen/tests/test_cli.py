import json
from pathlib import Path
import secrets

from datagen import __main__ as cli


def test_cli_safe_failure_never_prints_driver_values(monkeypatch, capsys):
    secret = secrets.token_urlsafe(32)
    def fail(*args):
        raise RuntimeError(secret)
    monkeypatch.setattr(cli, "build", fail)
    assert cli.main([]) == 2
    output = capsys.readouterr()
    assert secret not in output.err and "Traceback" not in output.err


def test_all_cli_success_modes_and_saved_checksum_guard(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    path = tmp_path / "evidence/datasets/baseline_test.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"baseline_checksum_sha256": "expected", "validation": {"source_checksum_sha256": "source"}}))
    calls = []
    monkeypatch.setattr(cli, "record", lambda *args: calls.append(args))
    monkeypatch.setattr(cli, "validate_database", lambda *args: {
        "passed": True, "checksum_sha256": "expected", "source_checksum_sha256": "source"})
    monkeypatch.setattr(cli, "build", lambda *args: {})
    monkeypatch.setattr(cli, "provision", lambda *args: {})
    monkeypatch.setattr(cli, "snapshot", lambda *args: {})
    for action in ("generate", "validate", "provision", "snapshot"):
        assert cli.main([action, "--db", "baseline_test", "--out", str(tmp_path / "private.dump")]) == 0
    assert calls[-1][1]["validation"]["matches_recorded_baseline"]
    assert "expected" not in capsys.readouterr().out
    monkeypatch.setattr(cli, "validate_database", lambda *args: {
        "passed": True, "checksum_sha256": "mutated", "source_checksum_sha256": "source"})
    assert cli.main(["validate", "--db", "baseline_test"]) == 2
    assert cli.main(["snapshot"]) == 2
