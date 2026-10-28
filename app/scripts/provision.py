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
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from service_app.config import Settings
from service_app.main import PASSWORDS
from service_app.models import User as PlainUser, protected_members
from service_app.protected_control import ProtectedUser, bindings, scopes
from service_app.policy import ROLES
from service_app.crypto import ToolkitAdapter
from infra.security import external_directory, secure_directory


def main():
    settings = Settings.from_env()
    User = ProtectedUser if settings.mode == "protected" else PlainUser
    base = external_directory(os.environ["DPR_PRIVATE_DIR"])
    # Restrict only the service-owned child, not an existing shared private directory.
    directory = secure_directory(base / "service-b")
    output = directory / f"service-b-{settings.mode}-accounts.json"
    url = settings.auth_database_url or settings.database_url
    if settings.mode == "protected":
        url = os.environ["APP_SETUP_DATABASE_URL"]
        setup, runtime = make_url(url), make_url(settings.database_url)
        if (setup.host, setup.port, setup.database) != (runtime.host, runtime.port, runtime.database):
            raise ValueError("Protected provisioning must use the same authorized target")
        if not settings.testing and (setup.query.get("sslmode") != "verify-full" or not setup.query.get("sslrootcert")):
            raise ValueError("Verified setup TLS required")
    engine = create_engine(url, hide_parameters=True)
    accounts = []
    with Session(engine) as db:
        if db.scalar(select(User.id).limit(1)):
            raise ValueError("Accounts already provisioned; refusing to overwrite")
        principal = os.environ["DEMO_MEMBER_PRINCIPAL"]
        if not principal.strip():
            raise ValueError("Set DEMO_MEMBER_PRINCIPAL to an authorized synthetic pengguna value")
        member_binding = principal
        crypto = None
        if settings.mode == "protected":
            crypto = ToolkitAdapter(settings)
            try:
                member_binding = crypto.blind_index("pengguna", principal)
            finally:
                crypto.close()
            # Trusted admin assigns explicit records; app_user never writes its own scope.
            legacy_ids = [int(v) for v in os.environ["DEMO_ASSIGNED_IDS"].split(",")]
            if not legacy_ids or len(legacy_ids) > 100 or any(v < 1 for v in legacy_ids):
                raise ValueError("Provide 1-100 explicit assigned legacy IDs")
            assigned = db.scalars(select(protected_members.c.anggota_id).where(protected_members.c.legacy_row_id.in_(legacy_ids))).all()
            if len(assigned) != len(set(legacy_ids)):
                raise ValueError("Some assigned records do not exist or are not visible to setup")
            own = db.scalars(select(protected_members.c.anggota_id).where(protected_members.c.pengguna_bidx == member_binding)).all()
            if len(own) != 1:
                raise ValueError("Member identity must match exactly one record")
        with output.open("x", encoding="utf-8") as stream:
            os.chmod(output, 0o600)
            for role in sorted(ROLES):
                password = secrets.token_urlsafe(24)
                username = role + ".demo"
                identifier = str(uuid.uuid4())
                values = dict(id=identifier, username=username, password_hash=PASSWORDS.hash(password), role=role, active=True)
                if settings.mode == "plain":
                    values["principal"] = member_binding if role == "anggota" else identifier
                db.add(User(**values))
                db.flush()
                if settings.mode == "protected":
                    if role == "anggota":
                        db.execute(bindings.insert().values(user_id=identifier, pengguna_bidx=member_binding))
                    ids = own if role == "anggota" else assigned if role in {"operator", "privileged_officer", "finance_officer"} else []
                    for record in ids:
                        for permission in (["read", "update"] if role != "finance_officer" else ["read"]):
                            db.execute(scopes.insert().values(principal=identifier, anggota_id=record, permission=permission, source_label="manual"))
                    if role == "privileged_officer":
                        db.execute(scopes.insert().values(principal=identifier, anggota_id=None, permission="insert", source_label="manual"))
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
