import base64
import json
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv


def decode_key(value: str) -> bytes:
    key = base64.b64decode(value, validate=True)
    if len(key) != 32:
        raise ValueError("Keys must contain exactly 32 random bytes")
    return key


@dataclass
class Settings:
    database_url: str = field(repr=False)
    encryption_keys: dict[int, bytes] = field(repr=False)
    blind_index_key: bytes = field(repr=False)
    key_version: int = 1
    crypto_provider: str = "local"
    app_origin: str = "http://localhost:3000"
    cookie_secure: bool = False
    session_ttl: int = 1800
    environment: str = "development"
    openbao_url: str = ""
    openbao_token: str = field(default="", repr=False)
    openbao_key: str = "dpr-members"

    @classmethod
    def from_env(cls):
        load_dotenv()
        keys = {int(k): decode_key(v) for k, v in json.loads(os.getenv("ENCRYPTION_KEYS", "{}")).items()}
        result = cls(
            database_url=os.environ["DATABASE_URL"], encryption_keys=keys,
            blind_index_key=decode_key(os.environ["BLIND_INDEX_KEY"]),
            key_version=int(os.getenv("ENCRYPTION_KEY_VERSION", "1")),
            crypto_provider=os.getenv("CRYPTO_PROVIDER", "local"),
            app_origin=os.getenv("APP_ORIGIN", "http://localhost:3000"),
            cookie_secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
            session_ttl=int(os.getenv("SESSION_TTL_SECONDS", "1800")),
            environment=os.getenv("ENVIRONMENT", "development"),
            openbao_url=os.getenv("OPENBAO_URL", ""), openbao_token=os.getenv("OPENBAO_TOKEN", ""),
            openbao_key=os.getenv("OPENBAO_KEY", "dpr-members"),
        )
        if result.crypto_provider == "local" and result.key_version not in keys:
            raise ValueError("Active encryption key missing")
        if any(k == result.blind_index_key for k in keys.values()):
            raise ValueError("Encryption and blind index keys must be separate")
        if result.environment != "development":
            if not result.cookie_secure or not result.app_origin.startswith("https://"):
                raise ValueError("Deployment requires HTTPS and Secure cookies")
            if result.crypto_provider == "local":
                raise ValueError("Local keys are restricted to development")
            from sqlalchemy.engine import make_url
            database = make_url(result.database_url)
            if database.get_backend_name() != "postgresql" or database.query.get("sslmode") != "verify-full" or not database.query.get("sslrootcert"):
                raise ValueError("Deployment PostgreSQL requires verify-full TLS and a trusted root CA")
        if result.session_ttl < 60:
            raise ValueError("Invalid session lifetime")
        return result
