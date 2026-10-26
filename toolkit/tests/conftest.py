import base64
import hashlib
import hmac
import json
import os
from types import SimpleNamespace

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import httpx
import pytest

from dprcrypto import OpenBaoClient
from infra.tls.make_ca import make_ca


@pytest.fixture(scope="session")
def ca_path(tmp_path_factory):
    directory = tmp_path_factory.mktemp("toolkit-ca")
    make_ca(directory)
    return directory / "ca.crt"


@pytest.fixture
def bao(monkeypatch, ca_path):
    state = SimpleNamespace(now=100.0, calls=[], mode=None, revoked=set(),
        keys={name: os.urandom(32) for name in ("pii-kek", "finance-kek")}, search=os.urandom(32))
    state.tokens = {name: os.urandom(24).hex() for name in ("svc-app", "svc-migration", "svc-verify", "root")}
    def handler(request):
        path = request.url.path
        state.calls.append(path)
        token = request.headers.get("X-Vault-Token")
        policy = next((name for name, value in state.tokens.items() if value == token), None)
        if policy is None or token in state.revoked or state.now >= 400:
            return httpx.Response(403, json={"errors": [token]})
        if path == "/v1/auth/token/lookup-self":
            return httpx.Response(200, json={"data": {"policies": [policy], "ttl": 400 - state.now, "explicit_max_ttl": 300}})
        if state.mode == "outage":
            raise httpx.ConnectError("sensitive detail", request=request)
        if state.mode == "redirect":
            return httpx.Response(307, headers={"Location": "https://elsewhere.test"})
        if state.mode == "bad_json":
            return httpx.Response(200, text="not JSON")
        if policy == "svc-verify" or (policy == "svc-migration" and "/decrypt/" in path):
            return httpx.Response(403, json={"errors": [token]})
        body = json.loads(request.content)
        if "context" in body:
            raise RuntimeError("Derivation context must not be used as AAD")
        key = path.rsplit("/", 1)[-1]
        if "/encrypt/" in path:
            nonce = os.urandom(12)
            aad = base64.b64decode(body["associated_data"]) if "associated_data" in body else None
            wrapped = nonce + AESGCM(state.keys[key]).encrypt(nonce, base64.b64decode(body["plaintext"]), aad)
            return httpx.Response(200, json={"data": {"ciphertext": "vault:v1:" + base64.b64encode(wrapped).decode()}})
        if "/decrypt/" in path:
            results = []
            for item in body["batch_input"]:
                raw = base64.b64decode(item["ciphertext"].split(":", 2)[2])
                aad = base64.b64decode(item["associated_data"]) if "associated_data" in item else None
                try:
                    plain = AESGCM(state.keys[key]).decrypt(raw[:12], raw[12:], aad)
                except Exception:
                    return httpx.Response(400, json={"errors": ["authentication failed"]})
                results.append({"plaintext": base64.b64encode(plain).decode(), "reference": item["reference"]})
            if state.mode == "partial":
                results[-1] = {"error": "withheld", "reference": str(len(results) - 1)}
            if state.mode == "reordered":
                results.reverse()
            if state.mode == "short_batch":
                results.pop()
            if state.mode == "bad_dek":
                results[0]["plaintext"] = base64.b64encode(os.urandom(31)).decode()
            return httpx.Response(200, json={"data": {"batch_results": results}})
        if "/hmac/" in path:
            digest = hmac.new(state.search, base64.b64decode(body["input"]), hashlib.sha256).digest()
            version = body["key_version"] if state.mode != "wrong_version" else body["key_version"] + 1
            return httpx.Response(200, json={"data": {"hmac": f"vault:v{version}:" + base64.b64encode(digest).decode()}})
        return httpx.Response(404)
    monkeypatch.setenv("OPENBAO_ADDR", "https://bao.example.test:8200")
    monkeypatch.setenv("OPENBAO_CACERT", str(ca_path))
    monkeypatch.setenv("OPENBAO_TOKEN", state.tokens["svc-app"])
    state.client = OpenBaoClient(transport=httpx.MockTransport(handler), clock=lambda: state.now)
    state.handler = handler
    yield state
    state.client.close()
