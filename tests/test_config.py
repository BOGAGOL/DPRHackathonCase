import base64
import json
import os

import pytest

from app.config import Settings


def env(monkeypatch):
    key = base64.b64encode(os.urandom(32)).decode()
    index = base64.b64encode(os.urandom(32)).decode()
    for name, value in {"DATABASE_URL": "postgresql+psycopg://synthetic@localhost/test", "ENCRYPTION_KEYS": json.dumps({"1": key}),
                        "BLIND_INDEX_KEY": index, "CRYPTO_PROVIDER": "local", "ENVIRONMENT": "development",
                        "COOKIE_SECURE": "false", "APP_ORIGIN": "http://localhost:3000", "SESSION_TTL_SECONDS": "1800", "ENCRYPTION_KEY_VERSION": "1"}.items():
        monkeypatch.setenv(name, value)
    return key


def test_config_key_separation_and_repr(monkeypatch):
    key = env(monkeypatch)
    settings = Settings.from_env()
    assert key not in repr(settings)
    monkeypatch.setenv("BLIND_INDEX_KEY", key)
    with pytest.raises(ValueError):
        Settings.from_env()


def test_deployment_requires_https_secure_and_database_tls(monkeypatch):
    env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(ValueError):
        Settings.from_env()
    monkeypatch.setenv("COOKIE_SECURE", "true")
    monkeypatch.setenv("APP_ORIGIN", "https://example.test")
    with pytest.raises(ValueError):
        Settings.from_env()
    monkeypatch.setenv("CRYPTO_PROVIDER", "openbao")
    with pytest.raises(ValueError):
        Settings.from_env()
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://synthetic@localhost/test?sslmode=verify-full&sslrootcert=/trusted/root.crt")
    assert Settings.from_env().cookie_secure
