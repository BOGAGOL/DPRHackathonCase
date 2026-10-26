"""Workload Transit client: verified TLS, expiring env identity, no root/no fallback."""

import base64
import hashlib
import math
import os
import re
import ssl
import threading
import time
from urllib.parse import urlsplit

import httpx

from .errors import CryptoError, OpenBaoError


KEKS = frozenset({"pii-kek", "finance-kek"})
SERVICE_POLICIES = frozenset({"svc-app", "svc-migration", "svc-verify", "key-operator"})


def validate_wrapped(value: str) -> str:
    try:
        if not isinstance(value, str) or not re.fullmatch(r"vault:v[1-9][0-9]*:[A-Za-z0-9+/]+={0,2}", value):
            raise ValueError()
        # For the two non-derived aes256-gcm96 KEKs: nonce + 32-byte DEK + tag.
        if len(base64.b64decode(value.split(":", 2)[2], validate=True)) != 60:
            raise ValueError()
        return value
    except (ValueError, TypeError):
        raise OpenBaoError() from None


def validate_dek(dek: bytes) -> bytes:
    if not isinstance(dek, (bytes, bytearray)) or len(dek) != 32:
        raise OpenBaoError()
    return bytes(dek)


class OpenBaoClient:
    def __init__(self, *, token_env: str = "OPENBAO_TOKEN", timeout: float = 5.0,
                 transport=None, clock=time.monotonic):
        try:
            address = os.environ["OPENBAO_ADDR"]
            ca_file = os.environ["OPENBAO_CACERT"]
            parsed = urlsplit(address)
            if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                    or parsed.query or parsed.fragment or parsed.path not in ("", "/")
                    or not ca_file or not token_env or not math.isfinite(timeout) or timeout <= 0):
                raise ValueError()
            context = ssl.create_default_context(cafile=ca_file)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            self._http = httpx.Client(base_url=address.rstrip("/"), verify=context,
                trust_env=False, follow_redirects=False, timeout=timeout, transport=transport)
        except (ValueError, TypeError, KeyError, OSError):
            raise OpenBaoError() from None
        self._token_env = token_env
        self._clock = clock
        self._lock = threading.RLock()
        self._closed = False
        self._epoch = 0
        self._fingerprint = None
        self._expires_at = 0.0

    def _reset(self) -> None:
        self._fingerprint = None
        self._expires_at = 0.0
        self._epoch += 1

    def _token(self) -> str:
        token = os.environ.get(self._token_env, "")
        if not token or not token.isascii() or any(c.isspace() for c in token) or len(token) > 4096:
            raise OpenBaoError()
        return token

    def _send(self, method: str, path: str, token: str, payload=None) -> dict:
        try:
            response = self._http.request(method, "/v1/" + path, json=payload,
                headers={"X-Vault-Token": token, "X-Vault-Request": "true"})
            if not 200 <= response.status_code < 300:
                raise OpenBaoError(response.status_code)
            result = response.json()["data"]
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            raise OpenBaoError() from None

    def authorization_scope(self) -> tuple[str, float]:
        """Opaque token partition + conservative monotonic expiry for DEK caches."""
        with self._lock:
            try:
                if self._closed:
                    raise OpenBaoError()
                token = self._token()
                fingerprint = hashlib.sha256(token.encode()).hexdigest()
                now = self._clock()
                if fingerprint != self._fingerprint:
                    self._reset()
                    identity = self._send("GET", "auth/token/lookup-self", token)
                    policies = identity["policies"]
                    ttl, maximum = identity["ttl"], identity["explicit_max_ttl"]
                    if (not isinstance(policies, list) or len(policies) != 1 or policies[0] not in SERVICE_POLICIES
                            or type(ttl) not in (int, float) or type(maximum) not in (int, float)
                            or not math.isfinite(ttl) or not math.isfinite(maximum)
                            or not 0 < ttl <= maximum <= 14400):
                        raise ValueError()
                    self._fingerprint = fingerprint
                    self._expires_at = now + ttl
                if self._clock() >= self._expires_at:
                    raise OpenBaoError()
                return f"{fingerprint}:{self._epoch}", self._expires_at
            except (KeyError, ValueError, TypeError, OpenBaoError):
                self._reset()
                raise OpenBaoError() from None

    def _call(self, path: str, payload: dict) -> dict:
        with self._lock:
            try:
                scope, _ = self.authorization_scope()
                token = self._token()
                if not scope.startswith(hashlib.sha256(token.encode()).hexdigest() + ":"):
                    raise OpenBaoError()
                return self._send("POST", path, token, payload)
            except OpenBaoError:
                self._reset()
                raise

    @staticmethod
    def _payload(kek: str, payload: dict, associated_data: bytes | None) -> dict:
        if kek not in KEKS or (associated_data is not None and not isinstance(associated_data, bytes)):
            raise CryptoError("Invalid KEK or associated data")
        if associated_data is not None:
            payload["associated_data"] = base64.b64encode(associated_data).decode("ascii")
        return payload

    def wrap(self, kek: str, dek: bytes, *, associated_data: bytes | None = None) -> str:
        payload = self._payload(kek, {"plaintext": base64.b64encode(validate_dek(dek)).decode("ascii")}, associated_data)
        try:
            return validate_wrapped(self._call(f"transit/encrypt/{kek}", payload)["ciphertext"])
        except KeyError:
            raise OpenBaoError() from None

    def unwrap_batch(self, kek: str, wrapped: list[str], *, associated_data: bytes | None = None) -> list[bytes]:
        if not isinstance(wrapped, list) or len(wrapped) > 100:
            raise CryptoError("Invalid unwrap batch size")
        items = [self._payload(kek, {"ciphertext": validate_wrapped(value), "reference": str(i)}, associated_data)
                 for i, value in enumerate(wrapped)]
        if not items:
            self._payload(kek, {}, associated_data)
            return []
        try:
            results = self._call(f"transit/decrypt/{kek}", {"batch_input": items})["batch_results"]
            if not isinstance(results, list) or len(results) != len(items):
                raise ValueError()
            decoded = []
            for i, item in enumerate(results):
                if item.get("error") or item.get("reference") != str(i):
                    raise ValueError()
                decoded.append(validate_dek(base64.b64decode(item["plaintext"], validate=True)))
            return decoded
        except (KeyError, ValueError, TypeError, AttributeError):
            raise OpenBaoError() from None

    def unwrap(self, kek: str, wrapped: str, *, associated_data: bytes | None = None) -> bytes:
        return self.unwrap_batch(kek, [wrapped], associated_data=associated_data)[0]

    def hmac(self, message: bytes, *, key_version: int = 1) -> bytes:
        if not isinstance(message, bytes) or type(key_version) is not int or key_version < 1:
            raise CryptoError("Invalid HMAC input or key version")
        try:
            result = self._call("transit/hmac/search-hmac/sha2-256", {
                "input": base64.b64encode(message).decode("ascii"), "key_version": key_version,
            })["hmac"]
            prefix, version, encoded = result.split(":", 2)
            if prefix != "vault" or version != f"v{key_version}":
                raise ValueError()
            digest = base64.b64decode(encoded, validate=True)
            if len(digest) != 32:
                raise ValueError()
            return digest
        except (KeyError, ValueError, TypeError, AttributeError):
            raise OpenBaoError() from None

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._reset()
            self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
