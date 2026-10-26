import base64
import json
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


@dataclass(frozen=True)
class CryptoEnvelope:
    format_version: int
    algorithm: str
    key_version: int
    nonce: bytes
    ciphertext_and_tag: bytes

    def encode(self) -> bytes:
        document = {
            "v": self.format_version,
            "alg": self.algorithm,
            "kv": self.key_version,
            "n": base64.b64encode(self.nonce).decode("ascii"),
            "ct": base64.b64encode(self.ciphertext_and_tag).decode("ascii"),
        }
        return json.dumps(document, separators=(",", ":"), sort_keys=True).encode("utf-8")

    @classmethod
    def decode(cls, payload: bytes):
        document = json.loads(payload.decode("utf-8"))
        if document.get("v") != 1:
            raise ValueError("unsupported_format_version")
        if document.get("alg") != "AES-256-GCM":
            raise ValueError("unsupported_algorithm")
        return cls(
            format_version=document["v"],
            algorithm=document["alg"],
            key_version=int(document["kv"]),
            nonce=base64.b64decode(document["n"], validate=True),
            ciphertext_and_tag=base64.b64decode(document["ct"], validate=True),
        )


class AESGCMCodec:
    def __init__(self, keys: dict[int, bytes]):
        if not keys:
            raise ValueError("at_least_one_key_required")
        for version, key in keys.items():
            if version < 1 or len(key) != 32:
                raise ValueError(f"invalid_key_version_{version}")
        self.keys = dict(keys)

    def encrypt(self, plaintext: bytes, aad: bytes, key_version: int) -> bytes:
        key = self.keys[key_version]
        nonce = os.urandom(12)
        ciphertext_and_tag = AESGCM(key).encrypt(nonce, plaintext, aad)
        return CryptoEnvelope(
            format_version=1,
            algorithm="AES-256-GCM",
            key_version=key_version,
            nonce=nonce,
            ciphertext_and_tag=ciphertext_and_tag,
        ).encode()

    def decrypt(self, payload: bytes, aad: bytes) -> bytes:
        envelope = CryptoEnvelope.decode(payload)
        try:
            key = self.keys[envelope.key_version]
        except KeyError as error:
            raise ValueError("unknown_key_version") from error
        try:
            return AESGCM(key).decrypt(
                envelope.nonce,
                envelope.ciphertext_and_tag,
                aad,
            )
        except InvalidTag as error:
            raise ValueError("ciphertext_authentication_failed") from error


def build_aad(tenant_id, table_name: str, column_name: str, record_id) -> bytes:
    return f"{tenant_id}|{table_name}|{column_name}|{record_id}".encode("utf-8")

