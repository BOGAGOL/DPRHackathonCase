"""Per-record local DEKs, Transit wrapping, atomic batch unwrap, bounded memory cache."""

from collections import OrderedDict
from dataclasses import dataclass
import math
import os
import threading
import time

from .errors import CryptoError, OpenBaoError
from .openbao import KEKS, validate_dek, validate_wrapped


@dataclass(frozen=True, repr=False)
class WrappedDEK:
    dek: bytes
    wrapped: str


@dataclass(frozen=True, repr=False)
class RecordKeys:
    pii: WrappedDEK
    finance: WrappedDEK


class KeyManager:
    def __init__(self, client, *, cache_ttl: float = 15.0, max_entries: int = 256,
                 batch_size: int = 100, clock=time.monotonic):
        if (not isinstance(cache_ttl, (int, float)) or not math.isfinite(cache_ttl) or not 0 <= cache_ttl <= 60
                or type(max_entries) is not int or not 0 <= max_entries <= 4096
                or type(batch_size) is not int or not 1 <= batch_size <= 100):
            raise CryptoError("Invalid DEK cache or batch bounds")
        self._client, self._clock = client, clock
        self._ttl, self._maximum, self._batch_size = cache_ttl, max_entries, batch_size
        self._cache = OrderedDict()
        self._scope = None
        self._lock = threading.RLock()
        self._closed = False
        self._hits = self._misses = self._remote_batches = 0

    def cache_stats(self) -> dict:
        """Aggregate counters only; no identifiers, wrapped keys, or plaintext DEKs."""
        with self._lock:
            total = self._hits + self._misses
            return {"hits": self._hits, "misses": self._misses,
                    "hit_rate": self._hits / total if total else 0.0,
                    "remote_batches": self._remote_batches, "entries": len(self._cache),
                    "max_entries": self._maximum, "ttl_seconds": self._ttl}

    def wrap(self, kek: str, dek: bytes) -> str:
        with self._lock:
            if self._closed or kek not in KEKS:
                raise OpenBaoError()
            return self._client.wrap(kek, validate_dek(dek))

    def new_dek(self, kek: str) -> WrappedDEK:
        dek = os.urandom(32)
        return WrappedDEK(dek, self.wrap(kek, dek))

    def create_record_keys(self) -> RecordKeys:
        return RecordKeys(self.new_dek("pii-kek"), self.new_dek("finance-kek"))

    def _discard(self, key) -> None:
        value, _ = self._cache.pop(key)
        value[:] = b"\x00" * len(value)

    def clear(self) -> None:
        with self._lock:
            for key in list(self._cache):
                self._discard(key)
            self._scope = None

    def unwrap_many(self, kek: str, wrapped: list[str]) -> list[bytes]:
        with self._lock:
            try:
                if self._closed or kek not in KEKS or not isinstance(wrapped, list):
                    raise OpenBaoError()
                for value in wrapped:
                    validate_wrapped(value)
                scope, token_expiry = self._client.authorization_scope()
                if scope != self._scope:
                    self.clear()
                    self._scope = scope
                now = self._clock()
                for key, (_, expiry) in list(self._cache.items()):
                    if now >= min(expiry, token_expiry):
                        self._discard(key)
                values, missing = {}, []
                for value in dict.fromkeys(wrapped):
                    key = (kek, value)
                    if key in self._cache:
                        self._hits += 1
                        values[value] = bytes(self._cache[key][0])
                        self._cache.move_to_end(key)
                    else:
                        self._misses += 1
                        missing.append(value)
                # No cache insertions or partial results until every batch succeeds.
                for start in range(0, len(missing), self._batch_size):
                    chunk = missing[start:start + self._batch_size]
                    decoded = self._client.unwrap_batch(kek, chunk)
                    self._remote_batches += 1
                    if not isinstance(decoded, list) or len(decoded) != len(chunk):
                        raise OpenBaoError()
                    values.update(zip(chunk, (validate_dek(dek) for dek in decoded)))
                current_scope, current_expiry = self._client.authorization_scope()
                if current_scope != scope or self._clock() >= min(token_expiry, current_expiry):
                    raise OpenBaoError()
                expiry = min(self._clock() + self._ttl, token_expiry, current_expiry)
                if self._ttl and self._maximum:
                    for value in missing:
                        key = (kek, value)
                        self._cache[key] = (bytearray(values[value]), expiry)
                        while len(self._cache) > self._maximum:
                            self._discard(next(iter(self._cache)))
                return [values[value] for value in wrapped]
            except (OpenBaoError, CryptoError):
                self.clear()
                raise

    def unwrap(self, kek: str, wrapped: str) -> bytes:
        return self.unwrap_many(kek, [wrapped])[0]

    def close(self) -> None:
        with self._lock:
            self.clear()
            self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
