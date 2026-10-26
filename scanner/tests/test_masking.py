import pytest

from scanner.masking import mask, normalize


@pytest.mark.parametrize("value,kind,expected", [
    ("Onno Purbo", "nama", "On*** Pu***"),
    ("3174010101901234", "nik", "3174********1234"),
    ("31740101901234", "nik", "3174******1234"),
    ("081234567890", "telepon", "0812****7890"),
    ("onno@example.com", "email", "on***@example.com"),
    ("1234567890124567", "rekening", "************4567"),
    ("12345678901234", "tidak_diketahui", "<14 digit>"),
    ("A", "nama", "***"),
    ("1234", "nik", "<4 digit>"),
    ("nama dengan email bocor@example.com", "email", "<35 campuran>"),
])
def test_mask(value, kind, expected):
    assert mask(value, kind) == expected
    assert value not in mask(value, kind)


@pytest.mark.parametrize("value,expected", [
    (" ZA.FI RA 123 ", "zafira"), ("Zafira", "zafira"),
    ("1234567890", "1234567890"), ("Naya-Ka", "nayaka"),
])
def test_normalize(value, expected):
    assert normalize(value) == expected
