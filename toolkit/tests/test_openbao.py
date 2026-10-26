import base64
import os
import ssl

import httpx
import pytest

from dprcrypto import CryptoError, OpenBaoClient, OpenBaoError
from dprcrypto.openbao import validate_dek, validate_wrapped


@pytest.mark.parametrize("address", ["http://localhost:8200", "https://u:p@localhost", "https://localhost/path", "https://localhost?token=x", "https://localhost#frag", "https://"])
def test_requires_verified_https_origin(address, monkeypatch, ca_path):
    monkeypatch.setenv("OPENBAO_ADDR", address)
    monkeypatch.setenv("OPENBAO_CACERT", str(ca_path))
    with pytest.raises(OpenBaoError):
        OpenBaoClient()


def test_tls_context_proxy_redirect_and_no_default_token_header(bao, monkeypatch):
    original = httpx.Client
    captured = {}
    def factory(**kwargs):
        captured.update(kwargs)
        return original(**kwargs)
    monkeypatch.setattr(httpx, "Client", factory)
    with OpenBaoClient(transport=httpx.MockTransport(bao.handler), clock=lambda: bao.now) as client:
        client.authorization_scope()
        assert captured["verify"].verify_mode == ssl.CERT_REQUIRED
        assert captured["verify"].check_hostname
        assert captured["verify"].minimum_version >= ssl.TLSVersion.TLSv1_2
        assert not captured["trust_env"] and not captured["follow_redirects"]
        assert "headers" not in captured
    with pytest.raises(OpenBaoError):
        client.authorization_scope()


def test_separate_token_environment(bao, monkeypatch):
    monkeypatch.setenv("MIGRATION_BAO_TOKEN", bao.tokens["svc-migration"])
    with OpenBaoClient(token_env="MIGRATION_BAO_TOKEN", transport=httpx.MockTransport(bao.handler), clock=lambda: bao.now) as client:
        wrapped = client.wrap("pii-kek", os.urandom(32))
        with pytest.raises(OpenBaoError):
            client.unwrap("pii-kek", wrapped)


def test_transit_roundtrip_optional_associated_data_and_batch(bao):
    key = os.urandom(32)
    wrapped = bao.client.wrap("pii-kek", key)
    assert validate_wrapped(wrapped) == wrapped
    assert bao.client.unwrap("pii-kek", wrapped) == key
    second = bao.client.wrap("finance-kek", os.urandom(32))
    assert len(bao.client.unwrap("finance-kek", second)) == 32
    aad = b"synthetic-wrapping-context"
    with_aad = bao.client.wrap("pii-kek", key, associated_data=aad)
    assert bao.client.unwrap("pii-kek", with_aad, associated_data=aad) == key
    with pytest.raises(OpenBaoError):
        bao.client.unwrap("pii-kek", with_aad)
    assert bao.client.unwrap_batch("pii-kek", []) == []


@pytest.mark.parametrize("mode", ["outage", "redirect", "bad_json", "partial", "reordered", "short_batch", "bad_dek"])
def test_errors_and_partial_batches_fail_closed_without_response_logs(bao, mode, caplog):
    wrapped = [bao.client.wrap("pii-kek", os.urandom(32)) for _ in range(2)]
    bao.mode = mode
    with pytest.raises(OpenBaoError) as caught:
        bao.client.unwrap_batch("pii-kek", wrapped)
    assert "sensitive detail" not in str(caught.value) + caplog.text
    assert all(token not in str(caught.value) + caplog.text for token in bao.tokens.values())


def test_expired_changed_missing_root_and_revoked_identity(bao, monkeypatch):
    first_scope, expiry = bao.client.authorization_scope()
    assert expiry == 400
    monkeypatch.setenv("OPENBAO_TOKEN", bao.tokens["svc-migration"])
    assert bao.client.authorization_scope()[0] != first_scope
    monkeypatch.setenv("OPENBAO_TOKEN", bao.tokens["root"])
    with pytest.raises(OpenBaoError):
        bao.client.authorization_scope()
    monkeypatch.delenv("OPENBAO_TOKEN")
    with pytest.raises(OpenBaoError):
        bao.client.authorization_scope()
    monkeypatch.setenv("OPENBAO_TOKEN", bao.tokens["svc-app"])
    bao.client.authorization_scope()
    bao.now = 400
    with pytest.raises(OpenBaoError):
        bao.client.authorization_scope()
    bao.now = 100
    bao.revoked.add(bao.tokens["svc-app"])
    with pytest.raises(OpenBaoError):
        bao.client.authorization_scope()


def test_malformed_inputs_and_hmac_result(bao, monkeypatch, ca_path):
    for value in (None, "vault:v0:any", "vault:v1:!!!!", "vault:v1:" + base64.b64encode(os.urandom(32)).decode()):
        with pytest.raises(OpenBaoError):
            validate_wrapped(value)
    for value in (b"", None, "not-bytes"):
        with pytest.raises(OpenBaoError):
            validate_dek(value)
    for kek in ("../pii-kek", "other-key"):
        with pytest.raises(CryptoError):
            bao.client.wrap(kek, os.urandom(32))
    with pytest.raises(CryptoError):
        bao.client.wrap("pii-kek", os.urandom(32), associated_data="not-bytes")
    with pytest.raises(CryptoError):
        bao.client.unwrap_batch("pii-kek", [""] * 101)
    with pytest.raises(CryptoError):
        bao.client.hmac("not-bytes")
    bao.mode = "wrong_version"
    with pytest.raises(OpenBaoError):
        bao.client.hmac(b"synthetic")
    for ttl in (0, float("nan"), -1):
        with pytest.raises(OpenBaoError):
            OpenBaoClient(timeout=ttl)
    monkeypatch.delenv("OPENBAO_CACERT")
    with pytest.raises(OpenBaoError):
        OpenBaoClient()


@pytest.mark.parametrize("identity", [
    {"policies": ["svc-app", "root"], "ttl": 300, "explicit_max_ttl": 300},
    {"policies": ["svc-app"], "ttl": 0, "explicit_max_ttl": 300},
    {"policies": ["svc-app"], "ttl": 300, "explicit_max_ttl": 0},
    {"policies": ["svc-app"], "ttl": 20000, "explicit_max_ttl": 20000},
    {"policies": ["svc-app"], "ttl": True, "explicit_max_ttl": 300},
])
def test_reject_unbounded_or_wrong_policy_tokens(bao, identity):
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"data": identity}))
    with OpenBaoClient(transport=transport) as client:
        with pytest.raises(OpenBaoError):
            client.authorization_scope()
