"""F-01: invented identities only; no external database or deployed account."""
from types import SimpleNamespace
import sqlite3

import pytest
from sqlalchemy import delete, select, func
from sqlalchemy.exc import IntegrityError

from conftest import csrf, invented_row, login
from service_app.models import protected_members
from service_app.protected_control import scopes
from service_app.repository import identity_conflict
from service_app.schemas import MemberInsert


@pytest.mark.parametrize("formatted", [False, True])
def test_existing_identity_conflicts_without_record_or_audit_value_leak(lab, formatted):
    login(lab, "privileged_officer")
    value = lab.rows[0]["no_ktp"]
    payload = invented_row(9)
    payload["no_ktp"] = "  " + value[:2] + "." + value[2:8] + "-" + value[8:] + "  " if formatted else value
    response = lab.client.post("/anggota", headers=csrf(lab.client), json=payload)
    assert response.status_code == 409
    assert response.json() == {"detail": "Data tidak dapat dibuat karena konflik identitas"}
    assert response.headers["cache-control"] == "no-store"
    assert value not in response.text and "anggota_id" not in response.text
    found = lab.client.get("/anggota/search", params={"no_ktp": value}).json()
    assert found["total"] == 1 and found["items"][0]["anggota_id"] == "1"
    assert lab.client.get("/anggota").json()["total"] == 3
    events = lab.audit_entries()
    assert any(e.action == "insert" and e.decision == "denied" for e in events)
    assert not any(e.action == "insert" and e.decision == "allowed" for e in events)
    assert not any(value in str(vars(e)) for e in events)


def test_hidden_existing_identity_still_conflicts_without_granting_scope(lab):
    if lab.mode != "protected":
        pytest.skip("Object scope applies to protected staff")
    login(lab, "privileged_officer")
    with lab.engine.begin() as db:
        owner = db.scalar(select(protected_members.c.anggota_id).where(protected_members.c.legacy_row_id == 1))
        db.execute(delete(scopes).where(scopes.c.principal == lab.users['privileged_officer'], scopes.c.anggota_id == owner))
        before = db.scalar(select(func.count()).select_from(scopes))
    assert lab.client.get("/anggota/1").status_code == 404
    payload = {**invented_row(9), "no_ktp": lab.rows[0]["no_ktp"]}
    assert lab.client.post("/anggota", headers=csrf(lab.client), json=payload).status_code == 409
    with lab.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(scopes)) == before
        assert db.scalar(select(func.count()).select_from(protected_members)) == 3


@pytest.mark.parametrize("identity", ["00123456780009", "0012345678000009"])
def test_new_formatted_identity_is_canonical_and_searchable_once(lab, identity):
    login(lab, "privileged_officer")
    payload = {**invented_row(9), "no_ktp": " " + identity[:2] + "." + identity[2:8] + "-" + identity[8:] + " "}
    created = lab.client.post("/anggota", headers=csrf(lab.client), json=payload)
    assert created.status_code == 201 and created.json()["no_ktp"] == identity
    assert lab.client.post("/anggota", headers=csrf(lab.client), json={**payload, "no_ktp": identity}).status_code == 409
    found = lab.client.get("/anggota/search", params={"no_ktp": identity}).json()
    assert found["total"] == 1 and len(found["items"]) == 1


@pytest.mark.parametrize("invalid", [12345678901234, "", "  ", "0012345678x0009", "0012345678000", "００１２３４５６７８０００９"])
def test_malformed_insert_identity_is_rejected_before_writing(lab, invalid):
    login(lab, "privileged_officer")
    assert lab.client.post("/anggota", headers=csrf(lab.client), json={**invented_row(9), "no_ktp": invalid}).status_code == 422
    assert lab.client.get("/anggota").json()["total"] == 3


@pytest.mark.parametrize("sqlstate, index, expected", [
    ("23505", "uq_anggota_protected_no_ktp_bidx", True),
    ("23505", "unrelated_unique_index", False),
    ("23503", "uq_anggota_protected_no_ktp_bidx", False),
])
def test_conflict_recognition_uses_only_sqlstate_and_expected_index(sqlstate, index, expected):
    error = IntegrityError('redacted', {}, SimpleNamespace(sqlstate=sqlstate, diag=SimpleNamespace(constraint_name=index)))
    assert identity_conflict(error) is expected


def test_sqlite_constraint_detection_does_not_match_unrelated_errors():
    with sqlite3.connect(':memory:') as db:
        db.execute('CREATE TABLE unrelated (id INTEGER UNIQUE)')
        db.execute('INSERT INTO unrelated VALUES (1)')
        with pytest.raises(sqlite3.IntegrityError) as caught:
            db.execute('INSERT INTO unrelated VALUES (1)')
    assert not identity_conflict(IntegrityError('redacted', {}, caught.value))


def test_schema_normalizes_before_max_length_without_trimming_zeroes():
    identity = "0012345678000009"
    row = MemberInsert.model_validate({**invented_row(9), "no_ktp": "  " + " ".join(identity) + "  "})
    assert row.no_ktp == identity


def test_unrelated_integrity_failure_stays_generic_503(lab, monkeypatch):
    from service_app.repository import MemberRepository
    def unrelated(*args, **kwargs):
        raise IntegrityError('withheld', {}, SimpleNamespace(sqlstate='23505', diag=SimpleNamespace(constraint_name='other_index')))
    monkeypatch.setattr(MemberRepository, 'insert', unrelated)
    login(lab, 'privileged_officer')
    response = lab.client.post('/anggota', headers=csrf(lab.client), json=invented_row(9))
    assert response.status_code == 503 and response.json() == {'detail': 'Layanan data tidak tersedia'}


def test_shared_contact_is_not_accidentally_made_unique(lab):
    login(lab, 'privileged_officer')
    payload = {**invented_row(9), 'email': lab.rows[0]['email']}
    assert lab.client.post('/anggota', headers=csrf(lab.client), json=payload).status_code == 201
