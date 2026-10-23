import base64
import hashlib
import json
import os
from pathlib import Path

import pytest

from app.crypto import DataProtectionService, LocalAESGCMProvider, OpenBaoTransitProvider, ProtectionError
from app.ingestion import COLUMNS, load_rows, parse_values, protect_rows, verify_rows
from app.policy import masked


@pytest.fixture
def crypto():
    return DataProtectionService(LocalAESGCMProvider({1: os.urandom(32)}), os.urandom(32))


def test_roundtrip_nonce_and_null(crypto):
    a = crypto.encrypt(1, "no_ktp", "00123456789012")
    b = crypto.encrypt(1, "no_ktp", "00123456789012")
    assert a != b
    assert crypto.decrypt(1, "no_ktp", a) == "00123456789012"
    assert crypto.encrypt(1, "email", None) is None
    assert crypto.decrypt(1, "email", None) is None


@pytest.mark.parametrize("context", [(2, "no_ktp"), (1, "rekening")])
def test_aad_binding(crypto, context):
    value = crypto.encrypt(1, "no_ktp", "canary")
    with pytest.raises(ProtectionError):
        crypto.decrypt(*context, value)


def test_tamper_and_wrong_key(crypto):
    envelope = crypto.encrypt(1, "email", "test@example.test")
    raw = bytearray(base64.b64decode(envelope["ciphertext"]))
    raw[0] ^= 1
    with pytest.raises(ProtectionError):
        crypto.decrypt(1, "email", {**envelope, "ciphertext": base64.b64encode(raw).decode()})
    wrong = DataProtectionService(LocalAESGCMProvider({1: os.urandom(32)}), os.urandom(32))
    with pytest.raises(ProtectionError):
        wrong.decrypt(1, "email", envelope)


def test_versions_and_provider_mixing(crypto):
    envelope = crypto.encrypt(1, "email", "canary")
    old_key = crypto.provider.keys[1]
    rotated = DataProtectionService(LocalAESGCMProvider({1: old_key, 2: os.urandom(32)}, 2), crypto.index_key)
    assert rotated.decrypt(1, "email", envelope) == "canary"
    assert rotated.encrypt(1, "email", "canary")["version"] == 2
    with pytest.raises(ProtectionError):
        crypto.decrypt(1, "email", {**envelope, "provider": "openbao-transit"})


def test_blind_index_normalization_key_separation(crypto):
    assert crypto.blind_index(" 001234 ") == crypto.blind_index("001234")
    assert crypto.blind_index("001234") != crypto.blind_index("1234")
    other = DataProtectionService(crypto.provider, os.urandom(32))
    assert other.blind_index("001234") != crypto.blind_index("001234")


def test_openbao_tls_and_outage_fail_closed(monkeypatch):
    with pytest.raises(ValueError):
        OpenBaoTransitProvider("http://untrusted.test", "dummy", "dpr-members")
    provider = OpenBaoTransitProvider("https://bao.example.test", "synthetic-test-token", "dpr-members")
    import httpx
    def unavailable(*args, **kwargs):
        raise httpx.ConnectError("unavailable")
    monkeypatch.setattr(httpx.Client, "post", unavailable)
    with pytest.raises(ProtectionError):
        provider.encrypt("canary", b"aad")


def test_transit_contract_uses_aad_and_versioned_envelope(monkeypatch):
    import httpx
    original_client = httpx.Client
    context = b"dpr:anggota:v1:1:email"
    def handler(request):
        payload = json.loads(request.content)
        assert payload["associated_data"] == base64.b64encode(context).decode()
        assert request.headers["X-Vault-Token"] == "synthetic-mock-token"
        if "/encrypt/" in request.url.path:
            assert base64.b64decode(payload["plaintext"]) == b"canary"
            return httpx.Response(200, json={"data": {"ciphertext": "vault:v7:synthetic-mock"}})
        return httpx.Response(200, json={"data": {"plaintext": base64.b64encode(b"canary").decode()}})
    def client(**kwargs):
        assert kwargs["verify"] is True and kwargs["trust_env"] is False
        return original_client(**kwargs, transport=httpx.MockTransport(handler))
    monkeypatch.setattr(httpx, "Client", client)
    provider = OpenBaoTransitProvider("https://bao.example.test", "synthetic-mock-token", "dpr-members")
    envelope = provider.encrypt("canary", context)
    assert envelope["provider"] == "openbao-transit" and envelope["version"] == 1
    assert provider.decrypt(envelope, context) == "canary"


def test_parser_preserves_quoted_null_zeros_escaping():
    assert parse_values("'NULL', NULL, '', '000123', 'O\\'Neil', 'a,b', 'a''b'") == ["NULL", None, "", "000123", "O'Neil", "a,b", "a'b"]
    with pytest.raises(ValueError):
        parse_values("'value'); DROP TABLE members; --")


def test_mask_never_reveals_short_value():
    assert masked("1234", "handphone") != "1234"
    assert masked("x@y", "email") != "x@y"


def test_complete_dataset_734x29(tmp_path, crypto):
    source = Path(__file__).resolve().parents[3] / "Task1_Hackathon_DPR_2026/Task1_Hackathon_DPR_2026/anggota_dummy.sql"
    if not source.exists():
        pytest.skip("Restricted organizer dataset not distributed with repository")
    try:
        rows = load_rows(source)
    except ValueError:
        pytest.fail("Organizer dataset parsing failed (source values withheld)", pytrace=False)
    assert len(rows) == 734 and len(COLUMNS) == 29
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.models import Base, Member
    engine = create_engine("sqlite:///" + str(tmp_path / "import.db"))
    Base.metadata.create_all(engine)
    checksum = hashlib.sha256(source.read_bytes()).hexdigest()
    with Session(engine) as db:
        assert protect_rows(db, crypto, rows, checksum)
        assert not protect_rows(db, crypto, rows, checksum)
        assert verify_rows(db, crypto, rows)["logical_equality"]
        envelopes = json.dumps(db.get(Member, 1).protected_fields)
        assert not any(rows[0][f] in envelopes for f in ["no_ktp", "rekening", "email"])
    engine.dispose()
