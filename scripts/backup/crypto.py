"""Bounded-memory AES-GCM frames; authenticate each frame before releasing bytes.

An authenticated empty final frame binds EOF. Header, sequence and length are AAD.
This outer backup format is independent of the contract's field ciphertext format.
"""

import hashlib
import hmac
import json
import os
import struct
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


MAGIC = b"DPRBAK01"
CHUNK = 1024 * 1024
HEADER = struct.Struct(">8s16sI")


class BackupError(RuntimeError):
    """Fixed error codes only; never include subprocess output or row values."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def key_id(key):
    return hashlib.sha256(key).hexdigest()[:24]


def cipher(key, identity):
    if not isinstance(key, bytes) or len(key) != 32:
        raise BackupError("invalid_backup_key")
    return AESGCM(HKDF(algorithm=hashes.SHA256(), length=32, salt=identity,
                      info=b"dpr|backup|v1").derive(key))


def read_exact(stream, count):
    result = bytearray()
    while len(result) < count:
        piece = stream.read(count - len(result))
        if not piece:
            raise BackupError("truncated_artifact")
        result.extend(piece)
    return bytes(result)


def encrypt_stream(source, destination, key, artifact_id):
    header = HEADER.pack(MAGIC, UUID(artifact_id).bytes, CHUNK)
    aes = cipher(key, UUID(artifact_id).bytes)
    destination.write(header)
    sequence = 0
    while True:
        piece = source.read(CHUNK)
        length = struct.pack(">I", len(piece))
        nonce = os.urandom(12)
        aad = header + struct.pack(">Q", sequence) + length
        destination.write(length + nonce + aes.encrypt(nonce, piece, aad))
        if not piece:
            break
        sequence += 1


def decrypt_stream(source, destination, key, artifact_id):
    header = read_exact(source, HEADER.size)
    magic, identity, chunk = HEADER.unpack(header)
    if magic != MAGIC or identity != UUID(artifact_id).bytes or chunk != CHUNK:
        raise BackupError("invalid_artifact_header")
    aes = cipher(key, identity)
    sequence = 0
    while True:
        length = read_exact(source, 4)
        size = struct.unpack(">I", length)[0]
        if size > CHUNK:
            raise BackupError("invalid_frame_size")
        nonce = read_exact(source, 12)
        encrypted = read_exact(source, size + 16)
        try:
            piece = aes.decrypt(nonce, encrypted, header + struct.pack(">Q", sequence) + length)
        except InvalidTag:
            raise BackupError("artifact_authentication_failed") from None
        if not size:
            if source.read(1):
                raise BackupError("trailing_artifact_bytes")
            break
        if destination is not None:
            destination.write(piece)
        sequence += 1


def file_digest(stream):
    digest = hashlib.sha256()
    size = 0
    while piece := stream.read(CHUNK):
        digest.update(piece)
        size += len(piece)
    return digest.hexdigest(), size


def sign_manifest(payload, key):
    if len(key) != 32:
        raise BackupError("invalid_manifest_key")
    return {"payload": payload, "hmac_sha256": hmac.new(key, canonical(payload), hashlib.sha256).hexdigest()}


def verify_manifest(document, key):
    try:
        if set(document) != {"payload", "hmac_sha256"}:
            raise ValueError()
        expected = sign_manifest(document["payload"], key)["hmac_sha256"]
        if not hmac.compare_digest(expected, document["hmac_sha256"]):
            raise ValueError()
        return document["payload"]
    except (ValueError, TypeError, KeyError):
        raise BackupError("manifest_authentication_failed") from None
