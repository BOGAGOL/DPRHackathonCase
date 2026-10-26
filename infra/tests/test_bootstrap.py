import io
import json
import os
from pathlib import Path
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest

from infra.openbao import init
from infra.openbao.api import BaoAPI, BaoError, NoRedirect, from_environment
from infra.tls.make_ca import make_ca


@pytest.fixture(scope="module")
def ca(tmp_path_factory):
    directory = tmp_path_factory.mktemp("api-ca")
    make_ca(directory)
    return str(directory / "ca.crt")


@pytest.mark.parametrize("address", ["http://localhost:8200", "https://u:p@localhost", "https://localhost/path", "https://localhost?x=1", "https://localhost#frag", "https://"])
def test_api_rejects_unsafe_origins(address, ca):
    with pytest.raises(ValueError):
        BaoAPI(address, ca)


def test_api_request_errors_redirects_and_env(ca, monkeypatch):
    monkeypatch.setenv("OPENBAO_ADDR", "https://localhost:8200")
    monkeypatch.setenv("OPENBAO_CACERT", ca)
    api = from_environment()
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = b'{"data": {"ok": true}}'
    api.opener = Mock()
    api.opener.open.return_value = response
    token = os.urandom(16).hex()
    assert api.request("/test", {"ok": True}, token=token)["data"]["ok"]
    req = api.opener.open.call_args.args[0]
    assert req.headers["X-vault-token"] == token
    assert json.loads(req.data) == {"ok": True}
    response.read.return_value = b""
    assert api.request("/test") == {}
    assert "X-vault-token" not in api.opener.open.call_args.args[0].headers
    for path in ("https://other.test", "//other", "/../else"):
        with pytest.raises(ValueError):
            api.request(path)
    for error, status in ((HTTPError("https://localhost", 403, "secret body", {}, io.BytesIO(b"private")), 403), (URLError("private"), 0)):
        api.opener.open.side_effect = error
        with pytest.raises(BaoError) as caught:
            api.request("/test")
        assert caught.value.status == status and "private" not in str(caught.value)
    assert NoRedirect().redirect_request(None, None, 302, "", {}, "https://other") is None


def test_initialize_saves_exclusively_without_unsealing(tmp_path):
    api = Mock()
    material = {"keys_base64": [os.urandom(32).hex() for _ in range(3)], "root_token": os.urandom(16).hex()}
    api.request.side_effect = [{"initialized": False}, material]
    init.initialize(api, tmp_path)
    assert json.loads((tmp_path / "openbao/init-material.json").read_text()) == material
    assert api.request.call_count == 2
    api.request.side_effect = [{"initialized": False}]
    with pytest.raises(FileExistsError):
        init.initialize(api, tmp_path)
    api.request.side_effect = [{"initialized": True}]
    with pytest.raises(ValueError):
        init.initialize(api, tmp_path)


def test_reserve_storage_before_remote_mutation(tmp_path):
    operation = Mock(side_effect=BaoError(500))
    path = tmp_path / "reserved.json"
    with pytest.raises(BaoError):
        init.save_response(path, operation)
    assert path.exists() and path.read_bytes() == b""
    with pytest.raises(FileExistsError):
        init.save_response(path, operation)
    assert operation.call_count == 1


def test_unseal_and_revoke_require_manual_share_and_correct_policy():
    api = Mock()
    with pytest.raises(ValueError):
        init.unseal(api, "")
    share = os.urandom(32).hex()
    init.unseal(api, share)
    api.request.assert_called_with("/sys/unseal", {"key": share})
    token = os.urandom(16).hex()
    api.request.return_value = {"data": {"policies": ["root"]}}
    with pytest.raises(ValueError):
        init.revoke_migration(api, token)
    api.request.return_value = {"data": {"policies": ["svc-migration"]}}
    init.revoke_migration(api, token)
    api.request.assert_called_with("/auth/token/revoke-self", {}, token=token)


def test_issue_tokens_have_bounded_ttl_and_no_default_policy(tmp_path):
    api = Mock()
    api.request.side_effect = [{"auth": {"client_token": os.urandom(16).hex()}} for _ in init.POLICIES]
    init.issue_tokens(api, os.urandom(16).hex(), tmp_path, 120)
    assert len(list((tmp_path / "openbao/tokens").glob("*.json"))) == 4
    for call, policy in zip(api.request.call_args_list, init.POLICIES):
        assert call.args[0] == "/auth/token/create-orphan"
        body = call.args[1]
        assert body["policies"] == [policy]
        assert body["no_default_policy"] and not body["renewable"]
        assert body["ttl"] == body["explicit_max_ttl"] == "120s"
    for ttl in (0, 59, 14401):
        with pytest.raises(ValueError):
            init.issue_tokens(api, "", tmp_path, ttl)


def configured_api(*, existing=False, unsafe=False, sealed=False, wrong_mount=False):
    api = Mock()
    def request(path, payload=None, **kwargs):
        if path == "/sys/seal-status":
            return {"sealed": sealed}
        if path == "/sys/mounts":
            return {"data": {"transit/": {"type": "kv" if wrong_mount else "transit"}} if existing else {}}
        if path.startswith("/transit/keys/") and payload is None:
            if not existing:
                # Creation becomes visible to the second read.
                name = path.rsplit("/", 1)[1]
                if not any(c.args[0] == path and len(c.args) > 1 for c in api.request.call_args_list):
                    raise BaoError(404)
            name = path.rsplit("/", 1)[1]
            return {"data": {"type": init.KEYS[name], "derived": False, "exportable": unsafe,
                             "allow_plaintext_backup": False, "deletion_allowed": False}}
        return {}
    api.request.side_effect = request
    return api


def test_configure_keys_policies_and_safe_reentry():
    for existing in (False, True):
        api = configured_api(existing=existing)
        init.configure(api, os.urandom(16).hex())
        policy_calls = [c for c in api.request.call_args_list if c.args[0].startswith("/sys/policies/acl/")]
        assert len(policy_calls) == 4
        created = [c for c in api.request.call_args_list if c.args[0].startswith("/transit/keys/") and len(c.args) > 1]
        assert len(created) == (0 if existing else 3)
    for kwargs in ({"sealed": True}, {"existing": True, "unsafe": True}, {"existing": True, "wrong_mount": True}):
        with pytest.raises(ValueError):
            init.configure(configured_api(**kwargs), "")


@pytest.mark.parametrize("command", ["init", "unseal", "configure", "issue", "revoke-migration", "status"])
def test_cli_dispatch_redacts_material(command, tmp_path, monkeypatch, capsys):
    api = Mock()
    api.request.return_value = {"initialized": True, "sealed": False, "version": "test"}
    monkeypatch.setattr(init, "from_environment", lambda: api)
    monkeypatch.setenv("DPR_SECRETS_DIR", str(tmp_path))
    token = os.urandom(16).hex()
    monkeypatch.setenv("OPENBAO_TOKEN", token)
    monkeypatch.setattr("sys.argv", ["init", command])
    monkeypatch.setattr(init.getpass, "getpass", lambda _: os.urandom(32).hex())
    for name in ("initialize", "configure", "issue_tokens", "revoke_migration"):
        monkeypatch.setattr(init, name, Mock())
    monkeypatch.setattr(init, "unseal", Mock(return_value={"sealed": False}))
    init.main()
    assert token not in capsys.readouterr().out
    monkeypatch.setattr(init, "from_environment", Mock(side_effect=BaoError(403)))
    with pytest.raises(SystemExit, match="No response data shown"):
        init.main()
