"""Missing dependencies and policy doubles must never become live-crypto PASS claims."""
import importlib.util
import json
from pathlib import Path
import secrets

import pytest


def load_readiness():
    path = Path(__file__).resolve().parents[1] / "scripts/check_ready.py"
    spec = importlib.util.spec_from_file_location("module_b_readiness_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def local_report(monkeypatch, tmp_path):
    module = load_readiness()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "APP", tmp_path / "app")
    return module


def test_missing_evidence_is_not_tested(tmp_path):
    module = load_readiness()
    assert module.evidence_status(tmp_path / "missing.json") == {"status": "NOT TESTED"}


@pytest.mark.parametrize("content", ["", "not json", "[]", '"PASSED"', "null", "1", '{}', '{"total": 10}',
                                     '{"status": null}', '{"status": []}', '{"status": "invented success"}'])
def test_invalid_evidence_never_passes(tmp_path, content):
    source = tmp_path / "invalid.json"
    source.write_text(content, encoding="utf-8")
    assert load_readiness().evidence_status(source) == {"status": "INVALID EVIDENCE"}


def test_invalid_bytes_directory_and_argument_do_not_echo_input(tmp_path):
    module = load_readiness()
    source = tmp_path / "invalid-utf8.json"
    source.write_bytes(b"\xff\xfe\x00")
    assert module.evidence_status(source) == {"status": "INVALID EVIDENCE"}
    assert module.evidence_status(tmp_path) == {"status": "INVALID EVIDENCE"}
    assert module.evidence_status(None) == {"status": "INVALID EVIDENCE"}


def test_evidence_export_drops_unknown_secret_or_payload_fields(tmp_path):
    canary = secrets.token_urlsafe(24)
    source = tmp_path / "evidence.json"
    source.write_text(json.dumps({"status": "PASSED", "total": 2, "counts": {"passed": 2},
                                  "password": canary, "token": canary, "responses": [canary], "traceback": canary}), encoding="utf-8")
    selected = load_readiness().evidence_status(str(source))
    assert selected == {"status": "PASSED", "total": 2, "counts": {"passed": 2}}
    assert canary not in json.dumps(selected)


def test_missing_module_a_dependencies_remain_explicit(monkeypatch, tmp_path):
    module = local_report(monkeypatch, tmp_path)
    report = module.report()
    assert not any(report["external_dependencies"].values())
    assert report["evidence"]["backend"]["status"] == "NOT TESTED"
    assert report["status"].startswith("PARTIAL")
    assert all(value.startswith("NOT TESTED") for value in report["target_integration"].values())


def test_passing_policy_doubles_cannot_certify_live_crypto(monkeypatch, tmp_path):
    module = local_report(monkeypatch, tmp_path)
    for directory in [tmp_path / "toolkit/dprcrypto", tmp_path / "policy", tmp_path / "docs/contracts"]:
        directory.mkdir(parents=True, exist_ok=True)
    (tmp_path / "policy/protection_profile.yaml").touch()
    (tmp_path / "docs/contracts/test_vectors.json").write_text("{}", encoding="utf-8")
    evidence = module.APP / "evidence/access-control"
    evidence.mkdir(parents=True)
    for name in ["unit-tests.json", "browser-tests.json", "postgres-tls.json"]:
        (evidence / name).write_text(json.dumps({"status": "PASSED", "scope": "Policy test using opaque-reference fake crypto"}), encoding="utf-8")
    report = module.report()
    assert all(report["external_dependencies"].values())
    assert report["evidence"]["backend"]["status"] == "PASSED"
    assert "fake crypto" in report["evidence"]["backend"]["scope"]
    assert report["target_integration"]["live_protected"].startswith("NOT TESTED")
    assert report["status"].startswith("PARTIAL")
    assert report["implementation"]["crypto_implementation_owner"] == "Module A"


def test_readiness_main_writes_machine_report_and_only_safe_stdout(monkeypatch, tmp_path, capsys):
    module = local_report(monkeypatch, tmp_path)
    module.main()
    result = json.loads((module.APP / "evidence/access-control/readiness.json").read_text())
    output = json.loads(capsys.readouterr().out)
    assert result["status"].startswith("PARTIAL")
    assert set(output) == {"status", "external_dependencies"}
