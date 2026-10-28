"""Validate Module A results without implementing any cryptographic operations."""
import secrets
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from service_app.crypto import CryptoUnavailable, checked_result
from service_app.models import User, protected_members
from service_app.repository import MemberRepository
from conftest import csrf, login


@pytest.mark.parametrize("kind", ["none", "short", "long", "string"])
def test_invalid_blind_index_cannot_be_used_as_lookup(kind):
    value = {"none": None, "short": secrets.token_bytes(31), "long": secrets.token_bytes(33), "string": secrets.token_hex(32)}[kind]
    with pytest.raises(CryptoUnavailable):
        checked_result("blind_index", value)


@pytest.mark.parametrize("kind", ["none", "tuple", "empty", "wrong_count", "short_key", "nonbytes"])
def test_unwrap_result_must_match_batch_and_aes256_key_size(kind):
    key = secrets.token_bytes(32)
    value = {"none": None, "tuple": (key,), "empty": [], "wrong_count": [key, key],
             "short_key": [secrets.token_bytes(16)], "nonbytes": [secrets.token_hex(16)]}[kind]
    with pytest.raises(CryptoUnavailable):
        checked_result("unwrap_many", value, ("pii", ["vault:v1:test-reference"]))


@pytest.mark.parametrize("value", [None, b"test", 0, {}, []])
def test_decrypting_nonnull_blob_must_return_text_never_null(value):
    with pytest.raises(CryptoUnavailable):
        checked_result("decrypt_field", value)


@pytest.mark.parametrize("kind", ["none", "string", "short", "wrong_version"])
def test_encrypt_result_requires_versioned_aead_blob(kind):
    value = {"none": None, "string": "unsupported", "short": b"\x01" + secrets.token_bytes(27),
             "wrong_version": b"\x02" + secrets.token_bytes(47)}[kind]
    with pytest.raises(CryptoUnavailable):
        checked_result("encrypt_field", value)


@pytest.mark.parametrize("kind", ["none", "missing_fin", "extra_domain", "wrong_key_size", "unwrapped_reference"])
def test_insert_keys_require_exact_domains_and_wrapped_key_metadata(kind):
    pair = (secrets.token_bytes(32), "vault:v1:" + str(uuid4()))
    values = {"none": None, "missing_fin": {"pii": pair}, "extra_domain": {"pii": pair, "fin": pair, "other": pair},
              "wrong_key_size": {"pii": (secrets.token_bytes(16), pair[1]), "fin": pair},
              "unwrapped_reference": {"pii": (pair[0], "local:" + str(uuid4())), "fin": pair}}
    with pytest.raises(CryptoUnavailable):
        checked_result("new_record_keys", values[kind])


def test_valid_contract_result_shapes_are_retained():
    key = secrets.token_bytes(32)
    blob = b"\x01" + secrets.token_bytes(28)
    wrapped = "vault:v7:" + str(uuid4())
    assert checked_result("blind_index", key) is key
    assert checked_result("unwrap_many", [key], ("pii", [wrapped])) == [key]
    assert checked_result("decrypt_field", "") == ""
    assert checked_result("encrypt_field", blob) is blob
    assert checked_result("new_record_keys", {"pii": (key, wrapped), "fin": (key, wrapped)})["pii"][1] == wrapped


@pytest.mark.parametrize("operation", ["decrypt", "encrypt", "blind_index", "unwrap"])
def test_bad_provider_result_is_generic_error_and_cannot_erase_record(lab, monkeypatch, operation):
    login(lab, "privileged_officer")
    if lab.mode == "plain":
        monkeypatch.setattr(lab.crypto, "decrypt_field", lambda *args, **kwargs: None)
        assert lab.client.get("/anggota/1").status_code == 200
        return
    with lab.engine.connect() as connection:
        previous = connection.execute(select(protected_members.c.email_ct).where(protected_members.c.legacy_row_id == 1)).scalar_one()
    if operation == "decrypt":
        monkeypatch.setattr(lab.crypto, "decrypt_field", lambda *args, **kwargs: None)
        response = lab.client.get("/anggota/1")
    elif operation == "encrypt":
        monkeypatch.setattr(lab.crypto, "encrypt_field", lambda *args, **kwargs: None)
        response = lab.client.patch("/anggota/1/kontak", headers=csrf(lab.client), json={"email": "replacement@example.test"})
    elif operation == "blind_index":
        monkeypatch.setattr(lab.crypto, "blind_index", lambda *args, **kwargs: None)
        response = lab.client.get("/anggota/search", params={"email": lab.rows[0]["email"]})
    else:
        monkeypatch.setattr(lab.crypto, "unwrap_many", lambda *args, **kwargs: [])
        response = lab.client.get("/anggota/1")
    assert response.status_code == 500 and set(response.json()) == {"detail"}
    assert lab.rows[0]["email"] not in response.text
    with lab.engine.connect() as connection:
        current = connection.execute(select(protected_members.c.email_ct).where(protected_members.c.legacy_row_id == 1)).scalar_one()
    assert current == previous


def test_production_member_scope_does_not_accept_raw_identifier():
    repo = MemberRepository("protected", crypto=None, testing=False)
    with pytest.raises(CryptoUnavailable):
        repo.scope(SimpleNamespace(id="00000000-0000-4000-8000-000000000001", role="anggota", principal="invented-raw-identifier"))
    with pytest.raises(CryptoUnavailable):
        repo.scope(SimpleNamespace(id="00000000-0000-4000-8000-000000000001", role="anggota", principal="bidx:v1:invalid"))


def test_stored_blind_index_binding_matches_only_own_record(lab):
    if lab.mode == "protected":
        expected = lab.crypto.blind_index("pengguna", lab.rows[0]["pengguna"])
        with DBSession(lab.engine) as db:
            from service_app.protected_control import bindings
            db.execute(bindings.update().where(bindings.c.user_id == lab.users["anggota"]).values(pengguna_bidx=expected))
            db.commit()
    login(lab, "anggota")
    assert lab.client.get("/anggota/1").status_code == 200
    assert lab.client.get("/anggota/2").status_code in (403, 404)
    assert lab.client.get("/anggota").json()["total"] == 1
