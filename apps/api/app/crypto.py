"""Authenticated, versioned field encryption; no plaintext fallback."""
import base64
import hashlib
import hmac
import os
import re
from abc import ABC, abstractmethod

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import Settings


class ProtectionError(Exception):
    pass


def aad(record_id: int, field: str) -> bytes:
    return f"dpr:anggota:v1:{record_id}:{field}".encode()


class CryptoProvider(ABC):
    @abstractmethod
    def encrypt(self, value: str, context: bytes) -> dict: ...

    @abstractmethod
    def decrypt(self, envelope: dict, context: bytes) -> str: ...


class LocalAESGCMProvider(CryptoProvider):
    def __init__(self, keys: dict[int, bytes], version: int = 1):
        if version not in keys or any(len(k) != 32 for k in keys.values()):
            raise ValueError("AES-256 keys required")
        self.keys, self.version = keys, version

    def encrypt(self, value: str, context: bytes) -> dict:
        nonce = os.urandom(12)
        data = AESGCM(self.keys[self.version]).encrypt(nonce, value.encode(), context)
        return {"provider": "local-aes256-gcm", "version": self.version,
                "nonce": base64.b64encode(nonce).decode(), "ciphertext": base64.b64encode(data).decode()}

    def decrypt(self, envelope: dict, context: bytes) -> str:
        try:
            if envelope["provider"] != "local-aes256-gcm":
                raise ValueError()
            nonce = base64.b64decode(envelope["nonce"], validate=True)
            data = base64.b64decode(envelope["ciphertext"], validate=True)
            return AESGCM(self.keys[envelope["version"]]).decrypt(nonce, data, context).decode()
        except Exception:
            raise ProtectionError("Protected data unavailable") from None


class OpenBaoTransitProvider(CryptoProvider):
    def __init__(self, url: str, token: str, key: str):
        if not url.startswith("https://") or not token or not re.fullmatch(r"[a-zA-Z0-9_-]+", key):
            raise ValueError("Transit requires HTTPS, an identity token and a valid key name")
        self.url, self.token, self.key = url.rstrip("/"), token, key

    def _call(self, operation: str, payload: dict) -> dict:
        try:
            with httpx.Client(timeout=5, verify=True, trust_env=False) as client:
                response = client.post(f"{self.url}/v1/transit/{operation}/{self.key}",
                                       headers={"X-Vault-Token": self.token}, json=payload)
                response.raise_for_status()
                return response.json()["data"]
        except Exception:
            raise ProtectionError("Protected data unavailable") from None

    def encrypt(self, value: str, context: bytes) -> dict:
        result = self._call("encrypt", {"plaintext": base64.b64encode(value.encode()).decode(),
                                       "associated_data": base64.b64encode(context).decode()})
        return {"provider": "openbao-transit", "version": 1, "key": self.key, "ciphertext": result["ciphertext"]}

    def decrypt(self, envelope: dict, context: bytes) -> str:
        if envelope.get("provider") != "openbao-transit" or envelope.get("key") != self.key or envelope.get("version") != 1:
            raise ProtectionError("Protected data unavailable")
        result = self._call("decrypt", {"ciphertext": envelope["ciphertext"],
                                       "associated_data": base64.b64encode(context).decode()})
        try:
            return base64.b64decode(result["plaintext"], validate=True).decode()
        except Exception:
            raise ProtectionError("Protected data unavailable") from None


class DataProtectionService:
    def __init__(self, provider: CryptoProvider, index_key: bytes):
        if len(index_key) != 32:
            raise ValueError("32-byte blind index key required")
        self.provider, self.index_key = provider, index_key

    def encrypt(self, record: int, field: str, value: str | None):
        return None if value is None else self.provider.encrypt(value, aad(record, field))

    def decrypt(self, record: int, field: str, envelope: dict | None):
        return None if envelope is None else self.provider.decrypt(envelope, aad(record, field))

    def blind_index(self, value: str) -> str:
        # Only outer whitespace removed. Preserve zeros, case, punctuation and synthetic length.
        normalized = value.strip()
        return hmac.new(self.index_key, b"dpr:no_ktp:v1\x00" + normalized.encode(), hashlib.sha256).hexdigest()


def build_protection(settings: Settings):
    provider = (LocalAESGCMProvider(settings.encryption_keys, settings.key_version)
                if settings.crypto_provider == "local" else
                OpenBaoTransitProvider(settings.openbao_url, settings.openbao_token, settings.openbao_key)
                if settings.crypto_provider == "openbao" else None)
    if provider is None:
        raise ValueError("Unknown crypto provider")
    return DataProtectionService(provider, settings.blind_index_key)
