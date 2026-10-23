from datetime import timedelta
import json

from sqlalchemy import select

from app.main import digest
from app.models import AuditEvent, Member, Session, User, utcnow
from conftest import csrf, login


def test_login_logout_and_token_hash(lab):
    app, client, password, _ = lab
    response = login(client, password)
    assert response.status_code == 200
    assert "HttpOnly" in response.headers.get_list("set-cookie")[0]
    token = client.cookies["dpr_session"]
    with app.state.session_factory() as db:
        assert db.scalar(select(User).where(User.username == "operator")).password_hash.startswith("$argon2id$")
        assert db.get(Session, digest(token)) is not None
        assert db.get(Session, token) is None
    assert client.get("/auth/me").json()["role"] == "operator"
    assert client.post("/auth/logout", headers=csrf(client)).status_code == 200
    client.cookies.set("dpr_session", token)
    assert client.get("/auth/me").status_code == 401


def test_https_cookie_flags(lab):
    app, client, password, _ = lab
    app.state.settings.cookie_secure = True
    client.base_url = "https://testserver"
    response = login(client, password)
    assert response.status_code == 200
    session_cookie = response.headers.get_list("set-cookie")[0]
    assert "Secure" in session_cookie and "HttpOnly" in session_cookie and "SameSite=strict" in session_cookie


def test_failed_login_same_message(lab):
    _, client, _, _ = lab
    client.get("/auth/csrf")
    a = client.post("/auth/login", json={"username": "operator", "password": "invalid"}, headers=csrf(client))
    b = client.post("/auth/login", json={"username": "unknown", "password": "invalid"}, headers=csrf(client))
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_expiration_and_revocation(lab):
    app, client, password, _ = lab
    login(client, password)
    with app.state.session_factory() as db:
        s = db.get(Session, digest(client.cookies["dpr_session"]))
        s.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert client.get("/anggota").status_code == 401


def test_unauthenticated_denied(lab):
    _, client, _, _ = lab
    for path in ["/anggota", "/anggota/1", "/dashboard/stats", "/audit/events", "/admin/users"]:
        assert client.get(path).status_code == 401


def test_idor_read_and_write(lab):
    _, client, password, _ = lab
    login(client, password)
    assert client.get("/anggota/2").status_code == 404
    assert client.patch("/anggota/2/contact", json={"revision": 1, "email": "new@example.test"}, headers=csrf(client)).status_code == 404
    assert client.get("/anggota").json()["total"] == 1


def test_operator_no_forbidden_fields(lab):
    _, client, password, rows = lab
    login(client, password)
    response = client.get("/anggota/1")
    data = response.json()
    assert set(data["fields"]) == {"email", "handphone", "telpon_jakarta", "telpon_daerah"}
    assert not any(rows[0][f] in response.text for f in ["no_ktp", "rekening", "email", "handphone"])
    assert "rekening" not in data["fields"]


def test_public_output_and_admin_no_implicit_sensitive(lab):
    _, client, password, _ = lab
    login(client, password, "viewer")
    assert client.get("/anggota").json()["total"] == 3
    assert client.get("/anggota/1").json()["fields"] == {}
    assert client.patch("/anggota/1/contact", json={"revision": 1, "email": "new@example.test"}, headers=csrf(client)).status_code == 403
    client.post("/auth/logout", headers=csrf(client))
    login(client, password, "admin")
    assert client.get("/anggota/1").status_code == 404
    assert client.get("/dashboard/stats").json()["visible_members"] == 0


def test_field_permission_explicit(lab):
    app, client, password, rows = lab
    login(client, password, "staff")
    data = client.get("/anggota/1").json()
    assert data["fields"]["no_ktp"] == rows[0]["no_ktp"]
    assert "rekening" not in data["fields"]
    with app.state.session_factory() as db:
        user = db.scalar(select(User).where(User.username == "staff"))
        user.permissions = [*user.permissions, "read:finance"]
        db.commit()
    assert client.get("/anggota/1").json()["fields"]["rekening"] == rows[0]["rekening"]


def test_sql_injection_and_wildcards(lab):
    _, client, password, _ = lab
    login(client, password, "viewer")
    for q in ["' OR 1=1 --", "%", "_"]:
        response = client.get("/anggota", params={"q": q})
        assert response.status_code == 200
        assert response.json()["total"] == 0
    assert client.get("/anggota", params={"sort": "nama; DROP TABLE members"}).status_code == 422
    assert client.get("/anggota").json()["total"] == 3


def test_csrf_login_patch_logout_and_search(lab):
    _, client, password, _ = lab
    assert client.post("/auth/login", json={"username": "operator", "password": password}).status_code == 403
    login(client, password)
    assert client.patch("/anggota/1/contact", json={"revision": 1, "email": "new@example.test"}).status_code == 403
    assert client.post("/auth/logout").status_code == 403
    assert client.post("/anggota/search/ktp", json={"no_ktp": "00123456789001"}).status_code == 403
    assert client.patch("/anggota/1/contact", json={"revision": 1, "email": "new@example.test"}, headers={**csrf(client), "Origin": "https://evil.test"}).status_code == 403


def test_csrf_bound_to_session(lab):
    _, client, password, _ = lab
    login(client, password)
    client.cookies.clear()
    # A forged double-submit pair cannot match the CSRF hash attached to the session.
    login(client, password)
    forged = "a" * 43
    for cookie in list(client.cookies.jar):
        if cookie.name == "dpr_csrf":
            client.cookies.delete(cookie.name, domain=cookie.domain, path=cookie.path)
    client.cookies.set("dpr_csrf", forged)
    assert client.post("/auth/logout", headers={"X-CSRF-Token": forged}).status_code == 403


def test_blind_search_scoped(lab):
    _, client, password, rows = lab
    login(client, password)
    response = client.post("/anggota/search/ktp", json={"no_ktp": "  " + rows[0]["no_ktp"] + "  "}, headers=csrf(client))
    assert [r["id"] for r in response.json()] == [1]
    response = client.post("/anggota/search/ktp", json={"no_ktp": rows[1]["no_ktp"]}, headers=csrf(client))
    assert response.json() == []
    assert client.get("/anggota/search", params={"no_ktp": rows[0]["no_ktp"]}).status_code == 422


def test_search_and_audit_permission(lab):
    _, client, password, _ = lab
    login(client, password, "viewer")
    assert client.post("/anggota/search/ktp", json={"no_ktp": "anything"}, headers=csrf(client)).status_code == 403
    assert client.get("/audit/events").status_code == 403
    assert client.get("/admin/users").status_code == 403


def test_update_encrypted_audit_safe_and_conflict(lab):
    app, client, password, rows = lab
    login(client, password)
    contact = "replacement@example.test"
    patch = {"revision": 1, "email": contact}
    assert client.patch("/anggota/1/contact", json=patch, headers=csrf(client)).status_code == 200
    assert client.patch("/anggota/1/contact", json=patch, headers=csrf(client)).status_code == 409
    with app.state.session_factory() as db:
        member = db.get(Member, 1)
        assert contact not in json.dumps(member.protected_fields)
        assert app.state.protection.decrypt(1, "email", member.protected_fields["email"]) == contact
        events = db.scalars(select(AuditEvent)).all()
        output = json.dumps([{k: v for k, v in e.__dict__.items() if k != "_sa_instance_state"} for e in events], default=str)
        assert not any(v in output for v in [contact, rows[0]["no_ktp"], rows[0]["rekening"], password, client.cookies["dpr_session"]])


def test_mass_assignment_and_safe_validation(lab):
    _, client, password, _ = lab
    login(client, password)
    assert client.patch("/anggota/1/contact", json={"revision": 1, "rekening": "forbidden"}, headers=csrf(client)).status_code == 422
    response = client.patch("/anggota/1/contact", json={"revision": 1, "email": "<script>alert(1)</script>"}, headers=csrf(client))
    assert response.status_code == 422
    assert "<script>" not in response.text
    assert client.patch("/anggota/1/contact", json={"revision": 1, "alamat_jakarta": "Unassigned field"}, headers=csrf(client)).status_code == 403


def test_decrypt_failure_closed_public_survives(lab):
    app, client, password, _ = lab
    with app.state.session_factory() as db:
        member = db.get(Member, 1)
        fields = dict(member.protected_fields)
        fields["email"] = {**fields["email"], "ciphertext": "invalid"}
        member.protected_fields = fields
        db.commit()
    login(client, password)
    assert client.get("/anggota/1").status_code == 503
    assert client.get("/anggota").status_code == 200


def test_admin_account_provision_and_revoke(lab):
    app, client, password, _ = lab
    login(client, password, "admin")
    response = client.post("/admin/users", json={"username": "new.staff", "password": password, "role": "staff", "permissions": ["read:contact"], "assignments": [1]}, headers=csrf(client))
    assert response.status_code == 201
    assert "password_hash" not in response.text and password not in response.text
    target_id = response.json()["id"]
    assert client.patch(f"/admin/users/{target_id}/access", json={"active": False, "permissions": [], "assignments": []}, headers=csrf(client)).status_code == 200
    assert client.post("/admin/users", json={"username": "invalid", "password": password, "role": "staff", "permissions": ["read:everything"]}, headers=csrf(client)).status_code == 422


def test_pagination_bounds_and_no_store(lab):
    _, client, password, _ = lab
    login(client, password, "viewer")
    response = client.get("/anggota?page=2&page_size=2&sort=id&direction=desc")
    assert [m["id"] for m in response.json()["items"]] == [1]
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/anggota?page_size=10000").status_code == 422
    assert set(response.json()["items"][0]) == {"id", "nama", "ruangan"}
