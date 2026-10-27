import base64
import os

import pytest

from scripts.backup import settings
from scripts.backup.crypto import BackupError


def test_backup_keys_validate_without_exposure(monkeypatch):
    values = [os.urandom(32), os.urandom(32)]
    for name, value in zip(settings.KEY_VARS, values): monkeypatch.setenv(name, base64.b64encode(value).decode())
    assert settings.backup_keys() == tuple(values)
    monkeypatch.setenv(settings.KEY_VARS[1], os.environ[settings.KEY_VARS[0]])
    with pytest.raises(BackupError): settings.backup_keys()
    monkeypatch.setenv(settings.KEY_VARS[1], "invalid")
    with pytest.raises(BackupError): settings.backup_keys()
    monkeypatch.delenv(settings.KEY_VARS[1])
    with pytest.raises(BackupError): settings.backup_keys()


def test_local_dpapi_initialization_preserves_existing(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "secure_directory", lambda path: (path.mkdir(parents=True, exist_ok=True) or path))
    stored = {}
    def fake_powershell(script, environment):
        if "DPR_CREDENTIAL_INPUT" in environment:
            stored[environment["DPR_CREDENTIAL_ROLE"]] = environment["DPR_CREDENTIAL_INPUT"]
            return '<SS synthetic-protected="yes"/>'
        return stored[environment["DPR_CREDENTIAL_ROLE"]]
    monkeypatch.setattr(settings, "powershell", fake_powershell)
    first = settings.local_keys(tmp_path, create=True)
    assert settings.local_keys(tmp_path, create=True) == first
    assert len(stored) == 2
    monkeypatch.setattr(settings, "powershell", lambda script, env: env["DPR_CREDENTIAL_INPUT"])
    with pytest.raises(BackupError): settings.local_keys(tmp_path / "unsafe", create=True)


def test_tls_parameters_and_local_role(tmp_path, monkeypatch):
    ca = tmp_path / "ca.crt"; ca.write_text("public-test-certificate")
    monkeypatch.setenv("PGSSLROOTCERT", str(ca)); monkeypatch.setenv("DPR_BACKUP_PASSWORD", os.urandom(32).hex())
    monkeypatch.setenv("DPR_RESTORE_PASSWORD", os.urandom(32).hex())
    monkeypatch.setenv("PGPORT", "5433")
    backup = settings.parameters("protected_734")
    assert backup["user"] == "backup_user" and backup["sslmode"] == "verify-full"
    assert settings.parameters("postgres", admin=True)["user"] == "postgres"
    monkeypatch.delenv("DPR_BACKUP_PASSWORD"); monkeypatch.delenv("DPR_RESTORE_PASSWORD")
    monkeypatch.setenv("DPR_SECRETS_DIR", str(tmp_path))
    secret = os.urandom(32).hex()
    monkeypatch.setattr(settings, "role_password", lambda root, role: secret)
    monkeypatch.setattr(settings, "load_password", lambda root: secret)
    assert settings.parameters("protected_734", local=True)["password"] == secret
    assert settings.parameters("postgres", admin=True, local=True)["password"] == secret
    with pytest.raises(BackupError): settings.parameters("protected_734")
    monkeypatch.setenv("PGSSLROOTCERT", str(tmp_path / "missing"))
    with pytest.raises(BackupError): settings.parameters("protected_734", local=True)


def test_store_dedicated_outside_repo(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "secure_directory", lambda path: (path.mkdir(parents=True, exist_ok=True) or path))
    store = settings.artifact_store(str(tmp_path / "archives"))
    assert settings.artifact_store(str(store)) == store
    nonempty = tmp_path / "other"; nonempty.mkdir(); (nonempty / "unrelated").touch()
    with pytest.raises(BackupError): settings.artifact_store(str(nonempty))
    (store / ".dpr-backup-store.json").write_text('{}')
    with pytest.raises(BackupError): settings.artifact_store(str(store))
    from infra.security import REPO
    with pytest.raises(ValueError): settings.artifact_store(str(REPO / "backup"))


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI only")
def test_real_windows_dpapi_roundtrip_and_no_plaintext(tmp_path, monkeypatch):
    for name in settings.KEY_VARS: monkeypatch.setenv(name, "temporary")
    keys = settings.local_keys(tmp_path, create=True)
    assert settings.local_keys(tmp_path, create=True) == keys
    serialized = b"".join(path.read_bytes() for path in (tmp_path/"backup-keys").glob("*.xml"))
    for key in keys:
        assert key not in serialized and base64.b64encode(key) not in serialized
