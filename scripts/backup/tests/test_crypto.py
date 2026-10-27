import io
import json
import os
import struct
from uuid import uuid4

import pytest

from scripts.backup.crypto import (BackupError, CHUNK, HEADER, canonical, cipher,
    decrypt_stream, encrypt_stream, file_digest, key_id, read_exact, sign_manifest, verify_manifest)


def artifact(data, key, identity):
    stream = io.BytesIO()
    encrypt_stream(io.BytesIO(data), stream, key, identity)
    return stream.getvalue()


@pytest.mark.parametrize("size", [0, 1, 511, CHUNK, CHUNK + 13, 2 * CHUNK])
def test_roundtrip_unique_nonces_and_no_plaintext(size):
    key = os.urandom(32); identity = str(uuid4()); data = os.urandom(size)
    first = artifact(data, key, identity); second = artifact(data, key, identity)
    assert first != second
    result = io.BytesIO()
    decrypt_stream(io.BytesIO(first), result, key, identity)
    assert result.getvalue() == data
    decrypt_stream(io.BytesIO(first), None, key, identity)
    if size > 100:
        assert data[:100] not in first


@pytest.mark.parametrize("offset", [0, 8, 24, 28, 32, 44, 100, -1])
def test_each_structure_tamper_fails(offset):
    key = os.urandom(32); identity = str(uuid4())
    encoded = bytearray(artifact(os.urandom(128), key, identity)); encoded[offset] ^= 1
    with pytest.raises(BackupError):
        decrypt_stream(io.BytesIO(encoded), io.BytesIO(), key, identity)


def test_truncation_trailing_reorder_and_wrong_key():
    key = os.urandom(32); identity = str(uuid4())
    encoded = artifact(os.urandom(CHUNK + 1), key, identity)
    end = HEADER.size + 4 + 12 + CHUNK + 16
    reordered = encoded[:HEADER.size] + encoded[end:-32] + encoded[HEADER.size:end] + encoded[-32:]
    for broken in [encoded[:HEADER.size], encoded[:-32], encoded[:-1], encoded+b"x", reordered]:
        with pytest.raises(BackupError):
            decrypt_stream(io.BytesIO(broken), None, key, identity)
    with pytest.raises(BackupError):
        decrypt_stream(io.BytesIO(encoded), None, os.urandom(32), identity)
    with pytest.raises(BackupError):
        decrypt_stream(io.BytesIO(encoded), None, key, str(uuid4()))


def test_no_unauthenticated_plaintext_is_released():
    key = os.urandom(32); identity = str(uuid4())
    encoded = bytearray(artifact(b"invented-private-canary", key, identity))
    encoded[50] ^= 1; sink = io.BytesIO()
    with pytest.raises(BackupError):
        decrypt_stream(io.BytesIO(encoded), sink, key, identity)
    assert sink.getvalue() == b""


def test_manifest_key_separation_and_canonicalization():
    key = os.urandom(32); payload = {"z": 2, "a": "synthetic"}
    signed = sign_manifest(payload, key)
    assert verify_manifest(json.loads(json.dumps(signed)), key) == payload
    assert canonical(payload) == b'{"a":"synthetic","z":2}'
    assert key_id(key) != key_id(os.urandom(32))
    for broken in [{}, {**signed, "extra": True}, {**signed, "hmac_sha256": None},
                   {**signed, "payload": {"z": 3}}]:
        with pytest.raises(BackupError): verify_manifest(broken, key)
    with pytest.raises(BackupError): verify_manifest(signed, os.urandom(32))
    with pytest.raises(BackupError): sign_manifest(payload, b"")
    with pytest.raises(BackupError): cipher(b"", uuid4().bytes)
    with pytest.raises(BackupError): read_exact(io.BytesIO(b"x"), 2)
    import hashlib
    assert file_digest(io.BytesIO(b"invented")) == (hashlib.sha256(b"invented").hexdigest(), 8)


def test_bounded_read_for_hostile_frame():
    key = os.urandom(32); identity = str(uuid4())
    header = HEADER.pack(b"DPRBAK01", uuid4().bytes, CHUNK)
    with pytest.raises(BackupError): decrypt_stream(io.BytesIO(header), None, key, identity)
    header = HEADER.pack(b"DPRBAK01", __import__("uuid").UUID(identity).bytes, CHUNK)
    with pytest.raises(BackupError, match="invalid_frame_size"):
        decrypt_stream(io.BytesIO(header + struct.pack(">I", 0xffffffff)), None, key, identity)
