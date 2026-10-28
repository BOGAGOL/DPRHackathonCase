import pytest
from sqlalchemy import delete, select
from service_app.models import protected_members
from service_app.protected_control import scopes, bindings
from conftest import login, csrf, invented_row


def test_protected_scope_removal_denies_staff_list_detail_search_and_patch(lab):
    if lab.mode == "plain":
        return
    with lab.engine.begin() as db:
        db.execute(delete(scopes).where(scopes.c.principal == lab.users["operator"]))
    login(lab, "operator")
    assert lab.client.get("/anggota").json()["total"] == 0
    assert lab.client.get("/anggota/1").status_code == 404
    assert lab.client.get("/anggota/search", params={"email": lab.rows[0]["email"]}).json()["total"] == 0
    assert lab.client.patch("/anggota/1/kontak", headers=csrf(lab.client), json={"email": "new@example.test"}).status_code == 404


def test_read_assignment_does_not_allow_update_or_insert(lab):
    if lab.mode == "plain":
        return
    with lab.engine.begin() as db:
        db.execute(delete(scopes).where(scopes.c.principal == lab.users["privileged_officer"], scopes.c.permission.in_(["update", "insert"])))
    login(lab, "privileged_officer")
    assert lab.client.get("/anggota/1").status_code == 200
    assert lab.client.patch("/anggota/1/kontak", headers=csrf(lab.client), json={"email": "new@example.test"}).status_code == 404
    assert lab.client.post("/anggota", headers=csrf(lab.client), json=invented_row(20)).status_code == 403


def test_member_binding_and_scope_are_both_required(lab):
    if lab.mode == "plain":
        return
    with lab.engine.begin() as db:
        db.execute(bindings.update().where(bindings.c.user_id == lab.users["anggota"]).values(
            pengguna_bidx=lab.crypto.blind_index("pengguna", lab.rows[1]["pengguna"])))
    login(lab, "anggota")
    assert lab.client.get("/anggota").json()["total"] == 0
    assert lab.client.get("/anggota/1").status_code == 404
    assert lab.client.get("/anggota/2").status_code == 404


def test_actual_module_a_vectors_pass():
    import json
    from pathlib import Path
    from dprcrypto.vectors import verify_document
    root = Path(__file__).resolve().parents[2]
    checks = verify_document(json.loads((root / "docs/contracts/test_vectors.json").read_text(encoding="utf-8")))
    assert checks and all(checks.values())
