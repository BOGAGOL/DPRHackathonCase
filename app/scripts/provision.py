"""Synthetic demo accounts; random passwords only in explicit private storage outside repository."""
import json
import os
from pathlib import Path
import secrets
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app/backend"))
sys.path.insert(0, str(ROOT))
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from service_app.config import Settings
from service_app.main import PASSWORDS
from service_app.models import User
from service_app.policy import ROLES
from service_app.crypto import ToolkitAdapter
from infra.security import external_directory, secure_directory


def main():
    settings = Settings.from_env()
    base = external_directory(os.environ["DPR_PRIVATE_DIR"])
    # Restrict only the service-owned child, not an existing shared private directory.
    directory = secure_directory(base / "service-b")
    output = directory / f"service-b-{settings.mode}-accounts.json"
    engine = create_engine(settings.auth_database_url or settings.database_url, hide_parameters=True)
    accounts = []
    with Session(engine) as db:
        if db.scalar(select(User.id).limit(1)):
            raise ValueError("Accounts already provisioned; refusing to overwrite")
        principal = os.environ["DEMO_MEMBER_PRINCIPAL"]
        if not principal.strip():
            raise ValueError("Set DEMO_MEMBER_PRINCIPAL to an authorized synthetic pengguna value")
        member_binding = principal
        if settings.mode == "protected":
            member_binding = "bidx:v1:" + ToolkitAdapter(settings).blind_index("pengguna", principal).hex()
        with output.open("x", encoding="utf-8") as stream:
            os.chmod(output, 0o600)
            for role in sorted(ROLES):
                password = secrets.token_urlsafe(24)
                username = role + ".demo"
                identifier = str(uuid.uuid4())
                db.add(User(id=identifier, username=username, password_hash=PASSWORDS.hash(password), role=role,
                            principal=member_binding if role == "anggota" else identifier))
                accounts.append({"username": username, "password": password, "role": role})
            json.dump(accounts, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
            db.commit()
    print("Six synthetic accounts provisioned; read the private file locally, not in chat/logs.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Provisioning failed ({type(exc).__name__}); values withheld.", file=sys.stderr)
        sys.exit(1)
