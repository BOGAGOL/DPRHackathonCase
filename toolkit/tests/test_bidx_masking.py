import hashlib
import hmac

import pytest

from dprcrypto import (BlindIndexer, CryptoError, index_message, normalize,
    mask_name, mask_nik, mask_phone, mask_email, mask_account)


@pytest.mark.parametrize("column,value,expected", [
    ("no_ktp", " 00-12 34 ", "001234"), ("no_ktp", "000000", "000000"),
    ("no_ktp", "", ""), ("email", "  UJI@Example.TEST  ", "uji@example.test"),
    ("email", " Straße@EXAMPLE.TEST ", "straße@example.test"),
    ("pengguna", "  AbC_001  ", "AbC_001"), ("email", None, None),
])
def test_exact_normalization_and_domain_message(column, value, expected):
    assert normalize(column, value) == expected
    assert index_message(column, value) == (None if expected is None else f"bidx|v1|{column}|{expected}".encode())


def test_remote_hmac_label_version_and_null(bao):
    indexer = BlindIndexer(bao.client)
    expected = hmac.new(bao.search, b"bidx|v1|no_ktp|001234", hashlib.sha256).digest()
    assert indexer.digest("no_ktp", "00-1234") == expected
    assert len(indexer.digest("email", "uji@example.test")) == 32
    assert indexer.digest("email", " UJI@EXAMPLE.TEST ") == indexer.digest("email", "uji@example.test")
    assert indexer.digest("pengguna", "Uji") != indexer.digest("pengguna", "uji")
    assert indexer.digest("email", "uji") != indexer.digest("pengguna", "uji")
    count = len(bao.calls)
    assert indexer.digest("email", None) is None and len(bao.calls) == count
    assert len(BlindIndexer(bao.client, key_version=2).digest("email", "uji")) == 32
    for version in (0, True, "1"):
        with pytest.raises(CryptoError):
            BlindIndexer(bao.client, key_version=version)
    for column, value in (("rekening", "test"), ("email", 42)):
        with pytest.raises(CryptoError):
            normalize(column, value)


@pytest.mark.parametrize("mask,value,expected", [
    (mask_name, "Onno Purbo", "On*** Pu***"), (mask_nik, "3174000011111234", "3174********1234"),
    (mask_phone, "081212347890", "0812****7890"), (mask_email, "onno@example.com", "on***@example.com"),
    (mask_account, "0000111122224567", "************4567"),
])
def test_required_masks(mask, value, expected):
    assert mask(value) == expected and mask(None) is None


def test_short_values_do_not_leak_complete_identifiers():
    assert mask_name("A Bo") == "*** B***"
    assert mask_name("") == ""
    assert mask_nik("12345678") == "********"
    assert mask_phone("1234") == "****"
    assert mask_account("1234") == "****"
    assert mask_email("a@example.test") == "***@example.test"
    assert mask_email("invalid") == "***"
