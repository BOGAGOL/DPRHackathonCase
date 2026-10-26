import os

from blind_index import blind_index, normalize_email, normalize_phone


def test_email_normalization_is_consistent():
    key = os.urandom(32)
    left = blind_index("email", normalize_email(" User@Example.Test "), key)
    right = blind_index("email", normalize_email("user@example.test"), key)
    assert left == right


def test_domain_separation():
    key = os.urandom(32)
    value = "user@example.test"
    assert blind_index("email", value, key) != blind_index("username", value, key)


def test_indonesian_phone_normalization():
    assert normalize_phone("0812-3456-7890") == "+6281234567890"

