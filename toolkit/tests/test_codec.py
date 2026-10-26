import os
from uuid import uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import pytest

from dprcrypto import CryptoError, DecryptionError, build_aad, decrypt, encrypt


@pytest.mark.parametrize("value", [None, "", "Anggota Uji Ω", "001122", "1985-06-17", "42"])
def test_exact_blob_and_roundtrip(value):
    dek, identity = os.urandom(32), uuid4()
    context = {"column": "nama", "anggota_id": identity}
    blob = encrypt(value, dek, **context)
    assert decrypt(blob, dek, **context) == value
    if value is None:
        assert blob is None
    else:
        assert blob[0] == 1 and len(blob) == 29 + len(value.encode())
        assert AESGCM(dek).decrypt(blob[1:13], blob[13:], build_aad(**context)).decode() == value
        assert decrypt(memoryview(blob), bytearray(dek), **context) == value


def test_exact_aad_and_random_nonces():
    identity, dek = uuid4(), os.urandom(32)
    expected = f"dpr|v1|anggota_protected|rekening|{identity}|1".encode()
    assert build_aad("rekening", str(identity).upper()) == expected
    blobs = [encrypt("synthetic", dek, column="rekening", anggota_id=identity) for _ in range(1024)]
    assert len({blob[1:13] for blob in blobs}) == 1024


@pytest.mark.parametrize("change", ["key", "record", "column", "protection_version", "format", "nonce", "ciphertext", "tag"])
def test_tamper_and_swap_fail_closed(change):
    dek = os.urandom(32)
    context = {"column": "email", "anggota_id": uuid4(), "protection_version": 1}
    blob = encrypt("uji@example.test", dek, **context)
    if change == "key":
        dek = os.urandom(32)
    elif change == "record":
        context["anggota_id"] = uuid4()
    elif change == "column":
        context["column"] = "rekening"
    elif change == "protection_version":
        context["protection_version"] = 2
    else:
        raw = bytearray(blob)
        raw[{"format": 0, "nonce": 1, "ciphertext": 13, "tag": len(raw) - 1}[change]] ^= 1
        blob = bytes(raw)
    with pytest.raises(DecryptionError, match="authentication failed"):
        decrypt(blob, dek, **context)


@pytest.mark.parametrize("blob", [b"", b"x" * 28, b"\x02" + b"x" * 28, "plaintext", 1])
def test_invalid_blob_never_becomes_plaintext(blob):
    with pytest.raises(DecryptionError):
        decrypt(blob, os.urandom(32), column="email", anggota_id=uuid4())


@pytest.mark.parametrize("column,identity,version", [
    ("email|injected", "not-uuid", 1), ("email", "not-uuid", 1),
    ("jenis_kelamin", str(uuid4()), 1), ("email", str(uuid4()), 0),
    ("email", str(uuid4()), True), ("email", str(uuid4()), 32768),
])
def test_invalid_context(column, identity, version):
    with pytest.raises(CryptoError):
        build_aad(column, identity, version)
    with pytest.raises(DecryptionError):
        decrypt(b"", os.urandom(32), column=column, anggota_id=identity, protection_version=version)


def test_invalid_input_key_and_authenticated_invalid_utf8():
    identity = uuid4()
    for key in (os.urandom(16), "" , None):
        with pytest.raises(CryptoError):
            encrypt("", key, column="email", anggota_id=identity)
        with pytest.raises(DecryptionError):
            decrypt(None, key, column="email", anggota_id=identity)
    with pytest.raises(CryptoError):
        encrypt(42, os.urandom(32), column="email", anggota_id=identity)
    key, nonce = os.urandom(32), os.urandom(12)
    blob = b"\x01" + nonce + AESGCM(key).encrypt(nonce, b"\xff", build_aad("email", identity))
    with pytest.raises(DecryptionError):
        decrypt(blob, key, column="email", anggota_id=identity)
