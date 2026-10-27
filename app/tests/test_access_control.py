"""Required Modul B access controls, checked against raw HTTP JSON and SQL projection."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import secrets

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event, select, update
from sqlalchemy.orm import Session as DBSession

from service_app.config import Settings
from service_app.main import create_app
from service_app.models import AuditLog, Session, User, baseline_members, protected_members
from conftest import COLUMNS, FINANCE, ROLES, csrf, invented_row, login

OPERATOR_FIELDS = {"anggota_id", "nama", "email", "handphone", "telpon_jakarta", "telpon_daerah", "no_ktp"}
FINANCE_FIELDS = {"anggota_id", "nama", "no_ktp", "rekening", "nama_rekening", "npwp", "kode_bank", "nama_bank", "nama_kppn"}
NONFINANCE_FIELDS = {"anggota_id", *COLUMNS} - FINANCE
DETAIL_FIELDS = {"operator": OPERATOR_FIELDS, "privileged_officer": NONFINANCE_FIELDS,
                 "finance_officer": FINANCE_FIELDS, "anggota": NONFINANCE_FIELDS}


def test_unauthenticated_routes_denied(lab):
    for path in ("/auth/me", "/anggota", "/anggota/1", "/analytics/summary", "/audit"):
        assert lab.client.get(path).status_code == 401


def test_login_cookie_flags_and_hashed_password(lab):
    response = login(lab)
    cookies = response.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith("dpr_session="))
    assert "HttpOnly" in session_cookie and "Secure" in session_cookie and "SameSite=strict" in session_cookie
    assert "Max-Age=" in session_cookie
    assert set(response.json()) == {"id", "username", "role"}
    assert lab.password not in response.text
    with DBSession(lab.engine) as db:
        user = db.get(User, lab.users["operator"])
        assert user.password_hash.startswith("$argon2id$")
        token = lab.client.cookies.get("dpr_session")
        assert db.get(Session, hashlib.sha256(token.encode()).hexdigest()) is not None
        assert db.get(Session, token) is None


def test_login_failure_does_not_enumerate_users(lab):
    lab.client.get("/auth/csrf")
    wrong = secrets.token_urlsafe(24)
    known = lab.client.post("/auth/login", headers=csrf(lab.client),
                            json={"username": "test-operator", "password": wrong})
    unknown = lab.client.post("/auth/login", headers=csrf(lab.client),
                              json={"username": "missing-user", "password": wrong})
    assert known.status_code == unknown.status_code == 401
    assert known.json() == unknown.json()
    assert wrong not in known.text


def test_repeated_failed_login_is_rate_limited(lab):
    lab.client.get("/auth/csrf")
    wrong = secrets.token_urlsafe(24)
    statuses = []
    for _ in range(35):
        response = lab.client.post("/auth/login", headers=csrf(lab.client),
                                   json={"username": "test-operator", "password": wrong})
        statuses.append(response.status_code)
        if response.status_code == 429:
            break
    assert 429 in statuses
    assert set(statuses) <= {401, 429}


def test_csrf_required_for_login_update_and_logout(lab):
    assert lab.client.post("/auth/login", json={"username": "test-operator", "password": lab.password}).status_code == 403
    login(lab)
    assert lab.client.patch("/anggota/1/kontak", json={"email": "replacement@example.test"}).status_code == 403
    assert lab.client.post("/auth/logout").status_code == 403
    assert lab.client.patch("/anggota/1/kontak", headers={**csrf(lab.client), "Origin": "https://untrusted.example.test"},
                            json={"email": "replacement@example.test"}).status_code == 403


def test_expired_session_and_logout_revocation(lab):
    login(lab)
    raw_token = lab.client.cookies.get("dpr_session")
    with DBSession(lab.engine) as db:
        session = db.get(Session, hashlib.sha256(raw_token.encode()).hexdigest())
        session.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
        db.commit()
    assert lab.client.get("/anggota").status_code == 401
    login(lab)
    raw_token = lab.client.cookies.get("dpr_session")
    assert lab.client.post("/auth/logout", headers=csrf(lab.client)).status_code == 200
    lab.client.cookies.set("dpr_session", raw_token)
    assert lab.client.get("/auth/me").status_code == 401


@pytest.mark.parametrize("role", ROLES)
def test_role_endpoint_field_matrix_raw_json(lab, role):
    login(lab, role)
    response = lab.client.get("/anggota/1")
    if role in {"analyst", "auditor"}:
        assert response.status_code == 403
        return
    assert response.status_code == 200
    body = response.json()
    assert set(body) == DETAIL_FIELDS[role]
    assert body["anggota_id"] == "1"
    original = lab.rows[0]
    if role in {"operator", "finance_officer"}:
        assert body["no_ktp"] != original["no_ktp"]
        assert original["no_ktp"] not in response.text
    if role == "operator":
        for field in ("email", "handphone", "telpon_jakarta", "telpon_daerah"):
            assert body[field] != original[field]
            assert original[field] not in response.text
        assert body["nama"] == original["nama"]
    elif role == "finance_officer":
        assert body["nama"] != original["nama"]
        assert all(body[field] == original[field] for field in FINANCE)
    else:
        assert all(body[field] == original[field] for field in COLUMNS if field not in FINANCE)
    forbidden = set(COLUMNS) - (DETAIL_FIELDS[role] - {"anggota_id"})
    assert not (set(body) & forbidden)


@pytest.mark.parametrize("role", ["operator", "privileged_officer", "finance_officer", "anggota"])
def test_list_names_masked_and_response_minimal(lab, role):
    login(lab, role)
    response = lab.client.get("/anggota")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "total", "page", "page_size"}
    assert body["page_size"] == 50
    assert all(set(member) == {"anggota_id", "nama"} for member in body["items"])
    assert body["total"] == (1 if role == "anggota" else 3)
    if role in {"operator", "finance_officer"}:
        assert all(row["nama"] not in response.text for row in lab.rows)
    else:
        assert body["items"][0]["nama"] == lab.rows[0]["nama"]


@pytest.mark.parametrize("role", ["analyst", "auditor"])
def test_non_record_roles_cannot_list_search_update_or_insert(lab, role):
    login(lab, role)
    assert lab.client.get("/anggota").status_code == 403
    assert lab.client.get("/anggota/search", params={"no_ktp": lab.rows[0]["no_ktp"]}).status_code == 403
    assert lab.client.patch("/anggota/1/kontak", headers=csrf(lab.client), json={"email": "replacement@example.test"}).status_code == 403
    assert lab.client.post("/anggota", headers=csrf(lab.client), json=invented_row(4)).status_code == 403


def test_anggota_cannot_read_or_modify_someone_else(lab):
    login(lab, "anggota")
    assert lab.client.get("/anggota/1").status_code == 200
    assert lab.client.get("/anggota/2").status_code in (403, 404)
    assert lab.client.patch("/anggota/2/kontak", headers=csrf(lab.client), json={"handphone": "081234567890"}).status_code in (403, 404)
    found = lab.client.get("/anggota/search", params={"email": lab.rows[1]["email"]})
    assert found.status_code in (200, 403, 404)
    if found.status_code == 200:
        assert found.json()["items"] == []


def test_finance_cannot_write_contacts(lab):
    login(lab, "finance_officer")
    assert lab.client.patch("/anggota/1/kontak", headers=csrf(lab.client), json={"email": "replacement@example.test"}).status_code == 403
    assert lab.client.post("/anggota", headers=csrf(lab.client), json=invented_row(4)).status_code == 403


def test_contact_patch_rejects_mass_assignment_and_invalid_format(lab):
    login(lab)
    assert lab.client.patch("/anggota/1/kontak", headers=csrf(lab.client), json={"rekening": "forbidden"}).status_code == 422
    assert lab.client.patch("/anggota/1/kontak", headers=csrf(lab.client), json={"email": "not-an-email"}).status_code == 422
    response = lab.client.patch("/anggota/1/kontak", headers=csrf(lab.client), json={"handphone": "<script>alert(1)</script>"})
    assert response.status_code == 422
    assert "<script>" not in response.text


def test_exact_lookup_normalization_and_no_partial_match(lab):
    login(lab, "privileged_officer")
    response = lab.client.get("/anggota/search", params={"no_ktp": lab.rows[0]["no_ktp"]})
    assert response.status_code == 200
    assert [r["anggota_id"] for r in response.json()["items"]] == ["1"]
    response = lab.client.get("/anggota/search", params={"email": "  " + lab.rows[0]["email"].upper() + "  "})
    assert response.status_code == 200
    assert [r["anggota_id"] for r in response.json()["items"]] == ["1"]
    response = lab.client.get("/anggota/search", params={"email": "example.test"})
    assert response.status_code == 422 or response.json()["items"] == []


def test_injection_payload_does_not_expand_result_scope(lab):
    login(lab, "privileged_officer")
    payload = "' OR 1=1; DROP TABLE anggota; --"
    for field in ("no_ktp", "email"):
        response = lab.client.get("/anggota/search", params={field: payload})
        assert response.status_code in (200, 422)
        assert payload not in response.text
        if response.status_code == 200:
            assert response.json()["items"] == []
    assert lab.client.get("/anggota").json()["total"] == 3


def test_contact_update_reindexes_email_and_retains_unmodified_data(lab):
    login(lab, "privileged_officer")
    changed = "replacement@example.test"
    previous = lab.rows[0]
    response = lab.client.patch("/anggota/1/kontak", headers=csrf(lab.client), json={"email": changed})
    assert response.status_code == 200
    assert response.json()["email"] == changed
    assert response.json()["handphone"] == previous["handphone"]
    assert response.json()["no_ktp"] == previous["no_ktp"]
    assert lab.client.get("/anggota/search", params={"email": changed.upper()}).json()["items"][0]["anggota_id"] == "1"
    assert lab.client.get("/anggota/search", params={"email": previous["email"]}).json()["items"] == []
    if lab.mode == "protected":
        with lab.engine.connect() as connection:
            row = connection.execute(select(protected_members.c.email_ct, protected_members.c.email_bidx).where(protected_members.c.legacy_row_id == 1)).one()
        assert changed.encode() not in row.email_ct
        assert row.email_bidx == lab.crypto.blind_index("email", changed)


def test_authorized_insert_and_role_denial(lab):
    login(lab, "privileged_officer")
    response = lab.client.post("/anggota", headers=csrf(lab.client), json=invented_row(4))
    assert response.status_code == 201
    assert response.json()["nama"] == invented_row(4)["nama"]
    assert not (set(response.json()) & FINANCE)
    assert lab.client.get("/anggota").json()["total"] == 4
    login(lab, "operator")
    assert lab.client.post("/anggota", headers=csrf(lab.client), json=invented_row(5)).status_code == 403


def test_future_birth_date_is_rejected_equally_before_either_mode_writes(lab):
    login(lab, "privileged_officer")
    payload = {**invented_row(4), "tanggal_lahir": "2027-01-01"}
    response = lab.client.post("/anggota", headers=csrf(lab.client), json=payload)
    assert response.status_code == 422
    assert lab.client.get("/anggota").json()["total"] == 3


def test_pagination_input_bounds(lab):
    login(lab)
    assert lab.client.get("/anggota?page=0").status_code == 422
    oversized = lab.client.get("/anggota?page_size=51")
    assert oversized.status_code in (200, 422)
    if oversized.status_code == 200:
        # Fixed page-size APIs may ignore unknown params; they must never expand the projection.
        assert oversized.json()["page_size"] == 50 and len(oversized.json()["items"]) <= 50
    body = lab.client.get("/anggota?page=2").json()
    assert body["page"] == 2 and body["items"] == [] and body["total"] == 3


def test_page_projection_and_batched_unwrap(lab):
    for i in range(4, 56):
        lab.add_member(i)
    login(lab, "finance_officer")
    statements = []
    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(lab.app.state.engine, "before_cursor_execute", capture)
    lab.crypto.unwrap_calls.clear()
    lab.crypto.decrypt_calls.clear()
    try:
        response = lab.client.get("/anggota")
    finally:
        event.remove(lab.app.state.engine, "before_cursor_execute", capture)
    assert response.status_code == 200 and len(response.json()["items"]) == 50
    if lab.mode == "plain":
        assert lab.crypto.unwrap_calls == []
    else:
        assert lab.crypto.unwrap_calls == [("pii", 50)]
        assert lab.crypto.decrypt_calls == ["nama"] * 50
        selects = [s.lower().split("from")[0] for s in statements if "anggota_protected" in s and s.lstrip().lower().startswith("select")]
        assert selects
        assert not any("dek_fin_wrapped" in s or "rekening_ct" in s or "email_ct" in s for s in selects)


def test_decrypt_swap_fails_generic_and_audited(lab):
    if lab.mode != "protected":
        pytest.skip("Ciphertext swap applies to protected mode only")
    login(lab, "privileged_officer")
    with lab.engine.begin() as connection:
        another = connection.execute(select(protected_members.c.nama_ct).where(protected_members.c.legacy_row_id == 2)).scalar_one()
        connection.execute(update(protected_members).where(protected_members.c.legacy_row_id == 1).values(nama_ct=another))
    response = lab.client.get("/anggota/1")
    assert response.status_code == 500
    assert set(response.json()) == {"detail"}
    assert not any(row["nama"] in response.text for row in lab.rows)
    assert "traceback" not in response.text.lower() and "context" not in response.text.lower()
    with DBSession(lab.engine) as db:
        events = db.scalars(select(AuditLog)).all()
        assert any("decrypt" in e.action.lower() and e.decision.lower() in {"error", "denied", "failed"} for e in events)


def test_audit_has_metadata_and_no_sensitive_values(lab):
    login(lab, "privileged_officer")
    assert lab.client.get("/anggota/1").status_code == 200
    with DBSession(lab.engine) as db:
        entries = db.scalars(select(AuditLog)).all()
        metadata = [{k: v for k, v in entry.__dict__.items() if k != "_sa_instance_state"} for entry in entries]
    serialized = json.dumps(metadata, default=str)
    forbidden = [lab.password, lab.client.cookies.get("dpr_session"), *[lab.rows[0][f] for f in ("no_ktp", "rekening", "email", "handphone")]]
    assert not any(value in serialized for value in forbidden)
    assert any(e["role"] == "privileged_officer" and e["anggota_id"] == "1" and e["request_id"] and e["field_class"] for e in metadata)


def test_security_headers_on_member_response(lab):
    login(lab)
    response = lab.client.get("/anggota/1")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    csp = response.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in csp and "unsafe-inline" not in csp


def test_oversized_body_is_rejected_with_security_headers(lab):
    response = lab.client.post("/auth/login", content="x" * 40000, headers={"Content-Type": "application/json"})
    assert response.status_code == 413
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-request-id"]


def test_analyst_and_auditor_only_their_endpoints(lab):
    login(lab, "analyst")
    summary = lab.client.get("/analytics/summary")
    assert summary.status_code == 200
    assert summary.json()["total"] == 3
    assert set(summary.json()) == {"total", "groups"}
    assert not any(r["nama"] in summary.text or r["no_ktp"] in summary.text for r in lab.rows)
    assert lab.client.get("/audit").status_code == 403
    login(lab, "auditor")
    audit = lab.client.get("/audit")
    assert audit.status_code == 200
    assert set(audit.json()) == {"items", "total", "page", "page_size"}
    assert lab.client.get("/analytics/summary").status_code == 403


def test_plain_and_protected_responses_match_for_authorized_roles(lab):
    other_mode = "protected" if lab.mode == "plain" else "plain"
    settings = Settings(mode=other_mode, database_url=str(lab.engine.url), testing=True)
    other_app = create_app(settings, crypto=lab.crypto)
    with TestClient(other_app, base_url="https://localhost:3443", raise_server_exceptions=False) as other_client:
        other = replace(lab, app=other_app, client=other_client, mode=other_mode)
        for role in ("operator", "privileged_officer", "finance_officer", "anggota"):
            login(lab, role)
            login(other, role)
            for path in ("/anggota", "/anggota/1"):
                a, b = lab.client.get(path), other.client.get(path)
                assert a.status_code == b.status_code == 200
                assert a.json() == b.json()
            a = lab.client.get("/anggota/search", params={"email": lab.rows[0]["email"]})
            b = other.client.get("/anggota/search", params={"email": lab.rows[0]["email"]})
            assert a.status_code == b.status_code and a.json() == b.json()
    for name in ("engine", "auth_engine", "analyst_engine", "auditor_engine"):
        engine = getattr(other_app.state, name, None)
        if engine is not None:
            engine.dispose()
