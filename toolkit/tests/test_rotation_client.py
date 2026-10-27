import base64
import json
import os

import httpx
import pytest

from dprcrypto import CryptoError, OpenBaoClient, OpenBaoError


def test_key_operator_metadata_rotate_and_rewrap(monkeypatch, ca_path):
    token = os.urandom(24).hex(); calls = []; latest = 1; mode = None
    monkeypatch.setenv("OPENBAO_ADDR", "https://operator.example.invalid")
    monkeypatch.setenv("OPENBAO_CACERT", str(ca_path)); monkeypatch.setenv("OPERATOR_TOKEN", token)
    wrapped = "vault:v1:"+base64.b64encode(os.urandom(60)).decode()
    def handler(request):
        nonlocal latest
        calls.append(request.url.path)
        assert request.headers["X-Vault-Token"] == token
        if request.url.path.endswith("lookup-self"):
            return httpx.Response(200, json={"data": {"policies": ["key-operator"], "ttl": 300, "explicit_max_ttl": 300}})
        if request.url.path.endswith("/rotate"):
            latest += 1
            return httpx.Response(204)
        if "/keys/" in request.url.path:
            data = {"type": "aes256-gcm96", "derived": False, "exportable": False,
                "allow_plaintext_backup": False, "deletion_allowed": False,
                "latest_version": latest, "min_decryption_version": 1, "min_encryption_version": 0}
            if mode == "unsafe": data["exportable"] = True
            if mode == "malformed": data.pop("latest_version")
            return httpx.Response(200, json={"data": data})
        body = json.loads(request.content)
        assert all(item["key_version"] == 2 for item in body["batch_input"])
        result = [{"reference": item["reference"], "ciphertext": "vault:v2:"+base64.b64encode(os.urandom(60)).decode()} for item in body["batch_input"]]
        if mode == "wrong_version": result[0]["ciphertext"] = wrapped
        if mode == "missing": result[0].pop("ciphertext")
        if mode == "partial": result[0]["error"] = "withheld"
        return httpx.Response(200, json={"data": {"batch_results": result}})
    with OpenBaoClient(token_env="OPERATOR_TOKEN", transport=httpx.MockTransport(handler)) as client:
        assert client.key_metadata("pii-kek")["latest_version"] == 1
        assert client.rotate_key("pii-kek")["latest_version"] == 2
        assert client.rewrap_batch("pii-kek", [wrapped], key_version=2)[0].startswith("vault:v2:")
        assert client.rewrap_batch("pii-kek", [], key_version=2) == []
        for bad in ("search-hmac", "../bad"):
            with pytest.raises(CryptoError): client.key_metadata(bad)
            with pytest.raises(CryptoError): client.rotate_key(bad)
        for value in (0, True, "2"):
            with pytest.raises(CryptoError): client.rewrap_batch("pii-kek", [wrapped], key_version=value)
        with pytest.raises(CryptoError): client.rewrap_batch("pii-kek", [wrapped]*101, key_version=2)
        for mode in ("wrong_version", "missing", "partial"):
            with pytest.raises(OpenBaoError): client.rewrap_batch("pii-kek", [wrapped], key_version=2)
        for mode in ("unsafe", "malformed"):
            with pytest.raises(OpenBaoError): client.key_metadata("pii-kek")
    assert not any("/decrypt/" in path or "/encrypt/" in path for path in calls)
