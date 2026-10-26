import base64
import json
import os
from unittest.mock import Mock

import pytest

from infra.openbao.api import BaoError
from infra.openbao import verify
from infra.openbao.init import POLICIES


def test_probe_detects_aad_ignored_and_authentication_failures():
    api = Mock()
    plain = os.urandom(32)
    api.request.side_effect = [
        {"data": {"ciphertext": "vault:v1:synthetic"}},
        {"data": {"plaintext": base64.b64encode(plain).decode()}},
        {}, BaoError(400),
    ]
    result = verify.probe_associated_data(api, os.urandom(16).hex())
    assert not result["roundtrip"] and not result["wrong_aad_rejected"] and result["missing_aad_rejected"]
    encrypt = api.request.call_args_list[0].args[1]
    assert "associated_data" in encrypt and "context" not in encrypt
    api.request.side_effect = BaoError(500)
    assert not verify.rejected(api, "/test", {}, "", 403)


def test_verification_refuses_wrong_identity_before_exercising_permissions():
    api = Mock()
    api.request.side_effect = [{"version": "2.5.5"}] + [{"data": {
        "policies": ["root"], "renewable": False, "orphan": True, "ttl": 100, "explicit_max_ttl": 100,
    }} for _ in POLICIES]
    report = verify.verify(api, {name: os.urandom(16).hex() for name in POLICIES})
    assert not report["passed"]
    assert api.request.call_count == 5
    assert all(len(call.args) == 1 for call in api.request.call_args_list)


def test_evidence_and_cli_failure(tmp_path, monkeypatch, capsys):
    path = tmp_path / "infra/report.json"
    verify.write_evidence({"passed": True}, path)
    assert json.loads(path.read_text())["passed"]
    monkeypatch.setattr(verify, "REPO", tmp_path)
    for policy in POLICIES:
        monkeypatch.delenv("OPENBAO_" + policy.upper().replace("-", "_") + "_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        verify.main()
    assert not json.loads((tmp_path / "evidence/infra/openbao.json").read_text())["passed"]
    for policy in POLICIES:
        monkeypatch.setenv("OPENBAO_" + policy.upper().replace("-", "_") + "_TOKEN", os.urandom(16).hex())
    monkeypatch.setattr(verify, "from_environment", Mock())
    monkeypatch.setattr(verify, "verify", Mock(return_value={"passed": True}))
    verify.main()
    assert "PASS" in capsys.readouterr().out
