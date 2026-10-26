import json
import os

import pytest

from crypto_codec import AESGCMCodec


def test_round_trip_and_random_nonce():
    codec = AESGCMCodec({1: os.urandom(32)})
    aad = b"tenant|table|email|record"
    plaintext = b"synthetic@example.test"
    first = codec.encrypt(plaintext, aad, 1)
    second = codec.encrypt(plaintext, aad, 1)
    assert first != second
    assert codec.decrypt(first, aad) == plaintext
    assert codec.decrypt(second, aad) == plaintext


def test_wrong_aad_is_rejected():
    codec = AESGCMCodec({1: os.urandom(32)})
    payload = codec.encrypt(b"secret", b"record-a", 1)
    with pytest.raises(ValueError, match="ciphertext_authentication_failed"):
        codec.decrypt(payload, b"record-b")


def test_tampering_is_rejected():
    codec = AESGCMCodec({1: os.urandom(32)})
    document = json.loads(codec.encrypt(b"secret", b"context", 1))
    document["ct"] = document["ct"][:-2] + "AA"
    payload = json.dumps(document).encode()
    with pytest.raises(ValueError):
        codec.decrypt(payload, b"context")


def test_unknown_key_version_is_rejected():
    source = AESGCMCodec({2: os.urandom(32)})
    reader = AESGCMCodec({1: os.urandom(32)})
    payload = source.encrypt(b"secret", b"context", 2)
    with pytest.raises(ValueError, match="unknown_key_version"):
        reader.decrypt(payload, b"context")

