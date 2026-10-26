import base64

import httpx


class OpenBaoClient:
    def __init__(
        self,
        address: str,
        token: str,
        key_name: str,
        timeout_seconds: float = 3.0,
        transport=None,
    ):
        self.key_name = key_name
        self.client = httpx.Client(
            base_url=address.rstrip("/"),
            headers={"X-Vault-Token": token},
            timeout=httpx.Timeout(timeout_seconds, connect=timeout_seconds),
            transport=transport,
            trust_env=False,
        )

    @staticmethod
    def _context(payload: dict, context: bytes | None):
        if context is not None:
            payload["context"] = base64.b64encode(context).decode("ascii")
        return payload

    def encrypt(self, plaintext: bytes, context: bytes | None = None) -> str:
        payload = self._context(
            {"plaintext": base64.b64encode(plaintext).decode("ascii")}, context
        )
        response = self.client.post(f"/v1/transit/encrypt/{self.key_name}", json=payload)
        response.raise_for_status()
        return response.json()["data"]["ciphertext"]

    def decrypt(self, ciphertext: str, context: bytes | None = None) -> bytes:
        payload = self._context({"ciphertext": ciphertext}, context)
        response = self.client.post(f"/v1/transit/decrypt/{self.key_name}", json=payload)
        response.raise_for_status()
        return base64.b64decode(response.json()["data"]["plaintext"], validate=True)

    def rewrap(self, ciphertext: str, context: bytes | None = None) -> str:
        payload = self._context({"ciphertext": ciphertext}, context)
        response = self.client.post(f"/v1/transit/rewrap/{self.key_name}", json=payload)
        response.raise_for_status()
        return response.json()["data"]["ciphertext"]

    def close(self):
        self.client.close()
