"""Exact lookup v1. Production HMAC remains inside OpenBao, pinned to key version 1."""

import re

from .errors import CryptoError


def normalize(column: str, value: str | None) -> str | None:
    if column not in ("no_ktp", "email", "pengguna") or (value is not None and not isinstance(value, str)):
        raise CryptoError("Invalid blind index input")
    if value is None:
        return None
    if column == "no_ktp":
        return re.sub(r"[^0-9]", "", value)
    if column == "email":
        return value.strip().lower()
    return value.strip()


def index_message(column: str, value: str | None) -> bytes | None:
    normalized = normalize(column, value)
    if normalized is None:
        return None
    return f"bidx|v1|{column}|{normalized}".encode("utf-8")


class BlindIndexer:
    def __init__(self, client, *, key_version: int = 1):
        if type(key_version) is not int or key_version < 1:
            raise CryptoError("A positive pinned HMAC key version is required")
        self._client = client
        self.key_version = key_version

    def digest(self, column: str, value: str | None) -> bytes | None:
        message = index_message(column, value)
        return None if message is None else self._client.hmac(message, key_version=self.key_version)
