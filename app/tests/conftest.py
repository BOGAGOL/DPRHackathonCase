"""Isolated, invented fixtures. Fake crypto is an HTTP policy test double only."""
from dataclasses import dataclass
from datetime import date
import os
from pathlib import Path
import secrets
import sys
from uuid import uuid4

from argon2 import PasswordHasher
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session as DBSession

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from service_app.config import Settings
from service_app.main import create_app
from service_app.models import Base, User, baseline_members, protected_members
from service_app.protected_control import ProtectedBase, ProtectedUser, bindings, scopes, audit_table

COLUMNS = "nama nama_lengkap nama_tanpa_gelar jenis_kelamin tempat_lahir tanggal_lahir tanggal_pernikahan no_ktp pekerjaan_terakhir alamat_jakarta telpon_jakarta alamat_daerah telpon_daerah handphone email ruangan status_kawin jumlah_anak jumlah_tanggungan jumlah_jiwa rekening nama_rekening npwp nama_kppn nip_kppn nama_bank kode_bank pengguna agama".split()
REF = {"jenis_kelamin", "pekerjaan_terakhir", "nama_kppn", "nama_bank"}
FINANCE = {"rekening", "nama_rekening", "npwp", "kode_bank"}
ROLES = ["operator", "privileged_officer", "finance_officer", "analyst", "auditor", "anggota"]


class FakeCrypto:
    """Opaque references, not encryption; never imported by application runtime.

    Validates record/column/version/key contexts so API tests can exercise swaps,
    domain minimisation and fail-closed behaviour without replacing Module A.
    """
    def __init__(self):
        self.wrapped = {}
        self.blobs = {}
        self.indexes = {}
        self.unwrap_calls = []
        self.decrypt_calls = []

    def new_record_keys(self):
        result = {}
        for domain in ("pii", "fin"):
            key, wrapped = os.urandom(32), "vault:v1:" + str(uuid4())
            self.wrapped[wrapped] = (domain, key)
            result[domain] = (key, wrapped)
        return result

    def unwrap_many(self, domain, wrapped):
        self.unwrap_calls.append((domain, len(wrapped)))
        values = []
        for token in wrapped:
            expected_domain, key = self.wrapped[token]
            if expected_domain != domain:
                raise ValueError("Test domain mismatch")
            values.append(key)
        return values

    def encrypt_field(self, value, dek, *, anggota_id, column, protection_version):
        blob = b"\x01" + os.urandom(47)
        self.blobs[blob] = (value, dek, str(anggota_id).lower(), column, protection_version)
        return blob

    def decrypt_field(self, blob, dek, *, anggota_id, column, protection_version):
        value, expected_dek, expected_id, expected_column, expected_version = self.blobs[bytes(blob)]
        context_ok = (expected_dek == dek and expected_id == str(anggota_id).lower()
                      and expected_column == column and expected_version == protection_version)
        if not context_ok:
            raise ValueError("Test authenticated context mismatch")
        self.decrypt_calls.append(column)
        return value

    def blind_index(self, field, value):
        normalized = value.strip()
        if field == "no_ktp":
            normalized = "".join(c for c in normalized if c.isdigit())
        elif field == "email":
            normalized = normalized.lower()
        return self.indexes.setdefault((field, normalized), os.urandom(32))


def invented_row(number):
    row = {field: f"uji-{field}-{number}" for field in COLUMNS}
    row.update(
        nama=f"Siti Anggota Uji {number}", nama_lengkap=f"Siti Anggota Uji {number}",
        nama_tanpa_gelar=f"Siti Anggota Uji {number}", jenis_kelamin="P", tempat_lahir="Kota Uji",
        tanggal_lahir="1985-04-15", tanggal_pernikahan=None, no_ktp=f"0012345678{number:04d}",
        pekerjaan_terakhir="Peneliti", alamat_jakarta=f"Jalan Uji Jakarta {number}",
        alamat_daerah=f"Jalan Uji Daerah {number}", telpon_jakarta=f"021{number:08d}",
        telpon_daerah=f"022{number:08d}", handphone=f"0812{number:08d}", email=f"anggota{number}@example.test",
        ruangan=f"UJI-{number:04d}", status_kawin="B", jumlah_anak="0", jumlah_tanggungan="0", jumlah_jiwa="1",
        rekening=f"00000000{number:08d}", nama_rekening=f"Pemilik Uji {number}", npwp=f"0000000{number:08d}",
        nama_kppn="KPPN Uji", nip_kppn=f"0000000000{number:08d}", nama_bank="Bank Uji", kode_bank="001",
        pengguna=f"pengguna-uji-{number}", agama="Buddha",
    )
    return row


@dataclass
class Lab:
    app: object
    client: TestClient
    engine: object
    password: str
    users: dict
    rows: list
    crypto: FakeCrypto
    mode: str

    def audit_entries(self):
        from types import SimpleNamespace
        from sqlalchemy import select
        from service_app.models import AuditLog
        with DBSession(self.engine) as db:
            if self.mode == "plain":
                return db.scalars(select(AuditLog)).all()
            return [SimpleNamespace(id=r.event_id, actor=r.actor, role=r.actor_role, action=r.action,
                    anggota_id=r.anggota_id, field_class=[r.field_class], decision=r.decision,
                    request_id=r.request_id, created_at=r.occurred_at)
                    for r in db.execute(select(audit_table))]

    def add_member(self, number, values=None):
        row = invented_row(number)
        if values:
            row.update(values)
        with self.engine.begin() as connection:
            connection.execute(baseline_members.insert().values(id=number, **row))
            identifier = str(uuid4())
            keys = self.crypto.new_record_keys()
            protected = {"anggota_id": identifier, "legacy_row_id": number, "protection_version": 1,
                         "dek_pii_wrapped": keys["pii"][1], "dek_fin_wrapped": keys["fin"][1],
                         "age_band": "40-49"}
            for field, value in row.items():
                if field in REF:
                    protected[field] = value
                else:
                    key = keys["fin" if field in FINANCE else "pii"][0]
                    protected[field + "_ct"] = None if value is None else self.crypto.encrypt_field(
                        value, key, anggota_id=identifier, column=field, protection_version=1)
            for field in ("no_ktp", "email", "pengguna"):
                protected[field + "_bidx"] = self.crypto.blind_index(field, row[field])
            connection.execute(protected_members.insert().values(**protected))
            for role, user_id in self.users.items():
                if role in {"operator", "privileged_officer", "finance_officer"} or (role == "anggota" and number == 1):
                    for permission in (["read"] if role == "finance_officer" else ["read", "update"]):
                        connection.execute(scopes.insert().values(principal=user_id, anggota_id=identifier, permission=permission))
        return row


@pytest.fixture(params=["plain", "protected"])
def lab(request, tmp_path):
    url = "sqlite:///" + str(tmp_path / "service-isolated.sqlite")
    settings = Settings(mode=request.param, database_url=url, testing=True)
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[table for table in Base.metadata.sorted_tables if table.name not in {"analyst_view", "audit_log"}])
    ProtectedBase.metadata.create_all(engine, tables=[table for table in ProtectedBase.metadata.sorted_tables if table.name != "audit_log"])
    (Base.metadata.tables["audit_log"] if request.param == "plain" else audit_table).create(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE VIEW analyst_view AS SELECT jenis_kelamin, pekerjaan_terakhir, nama_kppn, nama_bank, '40-49' AS age_band FROM anggota"))
        connection.execute(text("CREATE TRIGGER test_creator_scope AFTER INSERT ON anggota_protected BEGIN INSERT INTO access_scope(principal,anggota_id,permission) SELECT principal,NEW.anggota_id,'read' FROM access_scope WHERE permission='insert' AND anggota_id IS NULL; INSERT INTO access_scope(principal,anggota_id,permission) SELECT principal,NEW.anggota_id,'update' FROM access_scope WHERE permission='insert' AND anggota_id IS NULL; END"))
    crypto = FakeCrypto()
    app = create_app(settings, crypto=crypto)
    password = secrets.token_urlsafe(24)
    password_hash = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash(password)
    users = {}
    with DBSession(engine) as db:
        for role in ROLES:
            user = User(id=str(uuid4()), username=f"test-{role}", password_hash=password_hash, role=role,
                        principal="pengguna-uji-1", active=True)
            db.add(user)
            users[role] = user.id
            db.add(ProtectedUser(id=user.id, username=user.username, password_hash=password_hash, role=role, active=True))
            db.flush()
            if role == "anggota":
                db.execute(bindings.insert().values(user_id=user.id, pengguna_bidx=crypto.blind_index("pengguna", "pengguna-uji-1")))
            if role == "privileged_officer":
                db.execute(scopes.insert().values(principal=user.id, anggota_id=None, permission="insert"))
        db.commit()
    with TestClient(app, base_url="https://localhost:3443", raise_server_exceptions=False) as client:
        fixture = Lab(app, client, engine, password, users, [], crypto, request.param)
        fixture.rows.extend([fixture.add_member(i) for i in (1, 2, 3)])
        crypto.unwrap_calls.clear()
        crypto.decrypt_calls.clear()
        yield fixture
    engine.dispose()
    for name in ("engine", "auth_engine", "analyst_engine", "auditor_engine"):
        owned = getattr(app.state, name, None)
        if owned is not None:
            owned.dispose()


def csrf(client):
    return {"X-CSRF-Token": client.cookies.get("dpr_csrf", "")}


def login(lab, role="operator"):
    lab.client.cookies.clear()
    lab.client.get("/auth/csrf")
    result = lab.client.post("/auth/login", headers=csrf(lab.client),
                             json={"username": f"test-{role}", "password": lab.password})
    assert result.status_code == 200
    return result
