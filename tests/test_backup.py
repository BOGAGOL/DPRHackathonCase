import importlib.util
import os
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag

spec = importlib.util.spec_from_file_location("backup", Path(__file__).resolve().parents[1] / "scripts/backup.py")
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


def test_backup_authenticated_and_independent():
    key = os.urandom(32)
    data = b"synthetic logical database canary"
    encrypted = backup.encrypt_dump(data, key)
    assert data not in encrypted
    assert backup.decrypt_dump(encrypted, key) == data
    with pytest.raises(InvalidTag):
        backup.decrypt_dump(encrypted, os.urandom(32))
    tampered = bytearray(encrypted)
    tampered[-1] ^= 1
    with pytest.raises(InvalidTag):
        backup.decrypt_dump(bytes(tampered), key)
