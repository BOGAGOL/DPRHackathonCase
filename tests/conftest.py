import os
import secrets

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.ingestion import COLUMNS, SENSITIVE
from app.main import PASSWORDS, create_app
from app.models import Assignment, Base, Member, User


@pytest.fixture
def lab(tmp_path):
    settings = Settings(database_url="sqlite:///" + str(tmp_path / "test.db"),
                        encryption_keys={1: os.urandom(32)}, blind_index_key=os.urandom(32))
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    password = secrets.token_urlsafe(20)
    rows = []
    with app.state.session_factory() as session:
        for i in [1, 2, 3]:
            row = {field: f"synthetic-{field}-{i}" for field in COLUMNS}
            row.update(nama=f"Anggota Uji {i}", ruangan=f"UJI-{i}", no_ktp=f"0012345678900{i}",
                       email=f"uji{i}@example.test", handphone="08123456789", rekening="0009988776655", tanggal_pernikahan=None)
            rows.append(row)
            session.add(Member(id=i, nama=row["nama"], ruangan=row["ruangan"], ktp_index=app.state.protection.blind_index(row["no_ktp"]),
                               protected_fields={field: app.state.protection.encrypt(i, field, row[field]) for field in SENSITIVE}))
        session.flush()
        for username, role, permissions in [("viewer", "public", []), ("operator", "operator", ["search:ktp", "write:contact"]),
                                             ("staff", "staff", ["search:ktp", "read:identity", "read:contact", "write:contact"]),
                                             ("admin", "admin", ["audit:read", "users:manage"])]:
            user = User(username=username, password_hash=PASSWORDS.hash(password), role=role, permissions=permissions)
            session.add(user)
            session.flush()
            if role in {"operator", "staff"}:
                session.add(Assignment(user_id=user.id, member_id=1))
        session.commit()
    with TestClient(app) as client:
        yield app, client, password, rows
    app.state.engine.dispose()


def login(client, password, username="operator"):
    client.get("/auth/csrf")
    return client.post("/auth/login", json={"username": username, "password": password}, headers=csrf(client))


def csrf(client):
    return {"X-CSRF-Token": client.cookies.get("dpr_csrf", "")}
