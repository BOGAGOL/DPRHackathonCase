"""CONTRACT v1: 0x01 || random nonce(12) || AES-256-GCM ciphertext || tag(16)."""

import os
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .errors import CryptoError, DecryptionError


ENCRYPTED_COLUMNS = frozenset({
    "nama", "nama_lengkap", "nama_tanpa_gelar", "tempat_lahir", "tanggal_lahir",
    "tanggal_pernikahan", "no_ktp", "alamat_jakarta", "alamat_daerah", "telpon_jakarta",
    "telpon_daerah", "handphone", "email", "ruangan", "status_kawin", "jumlah_anak",
    "jumlah_tanggungan", "jumlah_jiwa", "rekening", "nama_rekening", "npwp", "kode_bank",
    "nip_kppn", "pengguna", "agama",
})


def build_aad(column: str, anggota_id: UUID | str, protection_version: int = 1) -> bytes:
    try:
        if column not in ENCRYPTED_COLUMNS or type(protection_version) is not int or not 1 <= protection_version <= 32767:
            raise ValueError()
        identity = UUID(str(anggota_id))
        if identity.version != 4:
            raise ValueError()
        return f"dpr|v1|anggota_protected|{column}|{identity}|{protection_version}".encode("utf-8")
    except (ValueError, TypeError, AttributeError):
        raise CryptoError("Invalid field identity or protection version") from None


def encrypt(value: str | None, dek: bytes, *, column: str, anggota_id: UUID | str,
            protection_version: int = 1) -> bytes | None:
    try:
        aad = build_aad(column, anggota_id, protection_version)
        if not isinstance(dek, (bytes, bytearray)) or len(dek) != 32:
            raise ValueError()
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError()
        nonce = os.urandom(12)
        return b"\x01" + nonce + AESGCM(dek).encrypt(nonce, value.encode("utf-8"), aad)
    except (ValueError, TypeError, OverflowError):
        raise CryptoError("Invalid field encryption input") from None


def decrypt(blob: bytes | None, dek: bytes, *, column: str, anggota_id: UUID | str,
            protection_version: int = 1) -> str | None:
    try:
        aad = build_aad(column, anggota_id, protection_version)
        if not isinstance(dek, (bytes, bytearray)) or len(dek) != 32:
            raise ValueError()
        if blob is None:
            return None
        if not isinstance(blob, (bytes, bytearray, memoryview)):
            raise ValueError()
        blob = bytes(blob)
        if len(blob) < 29 or blob[0] != 1:
            raise ValueError()
        return AESGCM(dek).decrypt(blob[1:13], blob[13:], aad).decode("utf-8")
    except (InvalidTag, ValueError, TypeError, OverflowError, CryptoError):
        raise DecryptionError("Protected field authentication failed") from None
