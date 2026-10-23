"""Generate checkout-local secrets without printing them. Never overwrite existing secrets."""
import base64
import json
import os
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parents[1]


def main():
    owner, app, baseline = (secrets.token_hex(24) for _ in range(3))
    key = lambda: base64.b64encode(os.urandom(32)).decode()
    values = {
        "POSTGRES_PASSWORD": owner, "APP_DB_PASSWORD": app, "BASELINE_DB_PASSWORD": baseline,
        "DATABASE_URL": f"postgresql+psycopg://app_user:{app}@127.0.0.1:55432/dpr_protected",
        "MIGRATION_DATABASE_URL": f"postgresql+psycopg://dpr_owner:{owner}@127.0.0.1:55432/dpr_protected",
        "BASELINE_DATABASE_URL": f"postgresql+psycopg://baseline_owner:{baseline}@127.0.0.1:55433/dpr_baseline",
        "ENCRYPTION_KEYS": json.dumps({"1": key()}), "ENCRYPTION_KEY_VERSION": "1", "BLIND_INDEX_KEY": key(),
        "CRYPTO_PROVIDER": "local", "COOKIE_SECURE": "false", "APP_ORIGIN": "http://localhost:3000",
        "ENVIRONMENT": "development", "SESSION_TTL_SECONDS": "1800",
    }
    with (ROOT / ".env").open("x", encoding="utf-8") as f:
        for name, value in values.items():
            f.write(f"{name}='{value}'\n")
    os.chmod(ROOT / ".env", 0o600)
    print("Created .env (ignored by Git). Keep a separate protected recovery copy.")


if __name__ == "__main__":
    main()
