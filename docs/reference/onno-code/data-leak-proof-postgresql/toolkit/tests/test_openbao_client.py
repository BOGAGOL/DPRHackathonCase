import base64

import httpx

from openbao_client import OpenBaoClient


def test_encrypt_request_uses_base64_and_context():
    def handler(request):
        assert request.url.path == "/v1/transit/encrypt/customer-data"
        assert request.headers["X-Vault-Token"] == "test-token"
        body = request.read().decode()
        assert base64.b64encode(b"secret").decode() in body
        return httpx.Response(200, json={"data": {"ciphertext": "vault:v1:test"}})

    client = OpenBaoClient(
        "http://openbao.test",
        "test-token",
        "customer-data",
        transport=httpx.MockTransport(handler),
    )
    assert client.encrypt(b"secret", b"context") == "vault:v1:test"
    client.close()


def test_decrypt_decodes_plaintext():
    def handler(_request):
        return httpx.Response(
            200,
            json={"data": {"plaintext": base64.b64encode(b"secret").decode()}},
        )

    client = OpenBaoClient(
        "http://openbao.test",
        "test-token",
        "customer-data",
        transport=httpx.MockTransport(handler),
    )
    assert client.decrypt("vault:v1:test") == b"secret"
    client.close()
