"""Workload Transit client: verified TLS, expiring env identity, no root/no fallback."""

import base64
import hashlib
import json
import math
import os
import re
import ssl
import threading
import time
from urllib.parse import urlsplit

import httpx

from .errors import CryptoError, OpenBaoError
from .https_pool import VerifiedHTTPSPool


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
            kind = os.environ.get('DPR_OPENBAO_HTTP_TRANSPORT', 'https_pool')
            if kind not in ('https_pool', 'httpx'):
                raise ValueError()
            self._transport_kind = 'custom' if transport is not None else kind
            self._transport = transport or (VerifiedHTTPSPool(address, context, timeout=timeout)
                                            if kind == 'https_pool' else None)
            self._http = httpx.Client(base_url=address.rstrip("/"), verify=context,
                trust_env=False, follow_redirects=False, timeout=timeout, transport=self._transport,
                limits=httpx.Limits(max_connections=8, max_keepalive_connections=8,
                                    keepalive_expiry=60.0))
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
            headers = {"X-Vault-Token": token, "X-Vault-Request": "true"}
            if isinstance(self._transport, VerifiedHTTPSPool):
                status, content = self._transport.request_bytes(method, '/v1/' + path, payload, headers)
            else:
                response = self._http.request(method, "/v1/" + path, json=payload, headers=headers)
                status, content = response.status_code, response.content
            if not 200 <= status < 300:
                raise OpenBaoError(status)
            if status == 204 and not content:
                return {}
            result = json.loads(content)["data"]
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

    def key_metadata(self, kek: str) -> dict:
        """Return safe envelope-key metadata only, using a key-operator identity."""
        if kek not in KEKS:
            raise CryptoError("Invalid KEK")
        self.require_policy("key-operator")
        with self._lock:
            data = self._send("GET", f"transit/keys/{kek}", self._token())
        try:
            if (data["type"] != "aes256-gcm96" or data["derived"] or data["exportable"]
                    or data["allow_plaintext_backup"] or data["deletion_allowed"]):
                raise ValueError()
            result = {name: data[name] for name in ("latest_version", "min_decryption_version", "min_encryption_version")}
            if any(type(value) is not int or value < (1 if name == "latest_version" else 0)
                   for name, value in result.items()):
                raise ValueError()
            return result
        except (KeyError, ValueError, TypeError):
            raise OpenBaoError() from None

    def rotate_key(self, kek: str) -> dict:
        """Non-idempotent operation: intentionally no automatic retry."""
        if kek not in KEKS:
            raise CryptoError("Invalid KEK")
        self.require_policy("key-operator")
        self._call(f"transit/keys/{kek}/rotate", {})
        return self.key_metadata(kek)

    def rewrap_batch(self, kek: str, wrapped: list[str], *, key_version: int) -> list[str]:
        if (kek not in KEKS or not isinstance(wrapped, list) or len(wrapped) > 100
                or type(key_version) is not int or key_version < 1):
            raise CryptoError("Invalid rewrap batch input")
        self.require_policy("key-operator")
        items = [{"ciphertext": validate_wrapped(value), "reference": str(i), "key_version": key_version}
                 for i, value in enumerate(wrapped)]
        results = self._batch_results(f"transit/rewrap/{kek}", items)
        try:
            values = [validate_wrapped(item["ciphertext"]) for item in results]
            if any(int(value.split(":", 2)[1][1:]) != key_version for value in values):
                raise ValueError()
            return values
        except (KeyError, ValueError, TypeError):
            raise OpenBaoError() from None

    def require_policy(self, expected: str) -> None:
        """Check workload separation without exposing a token or identity payload."""
        if expected not in SERVICE_POLICIES:
            raise OpenBaoError()
        with self._lock:
            self.authorization_scope()
            identity = self._send("GET", "auth/token/lookup-self", self._token())
            if identity.get("policies") != [expected]:
                raise OpenBaoError()

    def _batch_results(self, path: str, items: list[dict], **options) -> list[dict]:
        if not isinstance(items, list) or len(items) > 100:
            raise CryptoError("Invalid Transit batch size")
        if not items:
            return []
        try:
            results = self._call(path, {"batch_input": items, **options})["batch_results"]
            if not isinstance(results, list) or len(results) != len(items):
                raise ValueError()
            if any(not isinstance(item, dict) or item.get("error") or item.get("reference") != str(i)
                   for i, item in enumerate(results)):
                raise ValueError()
            return results
        except (KeyError, ValueError, TypeError):
            raise OpenBaoError() from None

    def wrap_batch(self, kek: str, deks: list[bytes]) -> list[str]:
        if kek not in KEKS or not isinstance(deks, list) or len(deks) > 100:
            raise CryptoError("Invalid wrap batch input")
        items = [{"plaintext": base64.b64encode(validate_dek(dek)).decode("ascii"), "reference": str(i)}
                 for i, dek in enumerate(deks)]
        try:
            return [validate_wrapped(item["ciphertext"]) for item in self._batch_results(f"transit/encrypt/{kek}", items)]
        except KeyError:
            raise OpenBaoError() from None

    def hmac_batch(self, messages: list[bytes], *, key_version: int = 1) -> list[bytes]:
        if (not isinstance(messages, list) or len(messages) > 100 or any(not isinstance(value, bytes) for value in messages)
                or type(key_version) is not int or key_version < 1):
            raise CryptoError("Invalid HMAC batch input")
        items = [{"input": base64.b64encode(message).decode("ascii"), "reference": str(i)}
                 for i, message in enumerate(messages)]
        try:
            results = self._batch_results("transit/hmac/search-hmac/sha2-256", items, key_version=key_version)
            values = []
            for item in results:
                prefix, version, encoded = item["hmac"].split(":", 2)
                digest = base64.b64decode(encoded, validate=True)
                if prefix != "vault" or version != f"v{key_version}" or len(digest) != 32:
                    raise ValueError()
                values.append(digest)
            return values
        except (KeyError, ValueError, TypeError, AttributeError):
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

    def connection_stats(self) -> dict:
        """Only aggregate connection counts; no TLS sessions, tokens, or key material."""
        with self._lock:
            return {'implementation': self._transport_kind,
                    **(self._transport.stats() if isinstance(self._transport, VerifiedHTTPSPool) else {})}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
