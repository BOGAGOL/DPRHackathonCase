"""Actual A+B backup -> fresh restore -> verified HTTPS, using invented records only."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
import secrets
import socket
import ssl
import sys
import threading
import time
from uuid import uuid4

import httpx
import psycopg
from psycopg import sql
import pytest

from dprcrypto import OpenBaoClient, decrypt
from infra.postgres.enable_tls import plaintext_rejected
from infra.security import REPO
from scripts.backup.crypto import BackupError
from scripts.backup.drills import tamper_test, retention_test
from scripts.backup.postgres import SERVICE_TABLES, drop_created_database, row_counts
from scripts.backup.runner import backup, restore
from .test_integration import laboratory


@contextmanager
def https_api(application, root):
    import uvicorn
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    address = "https://127.0.0.1:"+str(listener.getsockname()[1])
    configuration = uvicorn.Config(application, ssl_certfile=str(root/"tls/server.crt"),
        ssl_keyfile=str(root/"tls/server.key"), access_log=False, log_level="critical")
    server = uvicorn.Server(configuration)
    worker = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
    worker.start()
    try:
        for _ in range(200):
            if server.started: break
            if not worker.is_alive(): raise RuntimeError("HTTPS test API failed to start")
            time.sleep(.05)
        else: raise RuntimeError("HTTPS test API startup timeout")
        with httpx.Client(base_url=address, verify=ssl.create_default_context(cafile=str(root/"tls/ca.crt")), timeout=10, follow_redirects=False) as client:
            yield client
    finally:
        server.should_exit = True
        worker.join(15)
        listener.close()
        if worker.is_alive(): raise RuntimeError("HTTPS test API cleanup timeout")


def test_https_helper_verifies_ca_and_stops_listener(tmp_path):
    from fastapi import FastAPI
    from infra.tls.make_ca import make_ca
    make_ca(tmp_path/"tls")
    application = FastAPI()
    @application.get("/probe")
    def probe():
        return {"ready":True}
    with https_api(application,tmp_path) as client:
        address = str(client.base_url)
        assert client.get("/probe").json() == {"ready":True}
        with httpx.Client(verify=ssl.create_default_context()) as untrusted:
            with pytest.raises(httpx.ConnectError): untrusted.get(address.rstrip("/")+"/probe")
    with httpx.Client(verify=ssl.create_default_context(cafile=str(tmp_path/"tls/ca.crt"))) as after:
        with pytest.raises(httpx.ConnectError): after.get(address.rstrip("/")+"/probe")


def test_service_backup_restore_https_flow(laboratory, monkeypatch):
    sys.path.insert(0, str(REPO/"app/backend"))
    from argon2 import PasswordHasher
    from sqlalchemy import create_engine
    from sqlalchemy.engine import URL
    from service_app.config import Settings
    from service_app.main import create_app
    from service_app.models import utcnow
    from service_app.policy import ROLES
    spec = importlib.util.spec_from_file_location("recovery_b_schema", REPO/"app/scripts/schema.py")
    schema = importlib.util.module_from_spec(spec); spec.loader.exec_module(schema)
    lab = laboratory; params = lab["params"]; container = lab["container"]
    token = os.environ["OPENBAO_VALIDATION_TOKEN"]
    monkeypatch.setenv("OPENBAO_TOKEN", token)
    def url(role, database):
        return URL.create("postgresql+psycopg", username=role,
            password=params["password"] if role == "dpr_bootstrap" else lab["passwords"][role],
            host=params["host"], port=params["port"], database=database,
            query={"sslmode":"verify-full", "sslrootcert":params["sslrootcert"]}).render_as_string(hide_password=False)
    report = {"schema_version":1, "passed":False,
        "scope":"17 invented rows; disposable PG18/OpenBao TLS, actual A+B seven-table schema, live HTTPS backend; not official migrated datasets or benchmark", "checks":{}}
    checks = report["checks"]; created = []
    try:
        engine = create_engine(url("dpr_bootstrap", "protected_734"), hide_parameters=True)
        try:
            schema.setup_protected(engine)
            schema.setup_protected(engine)
        finally: engine.dispose()
        password = secrets.token_urlsafe(24)
        hashed = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash(password)
        identities = {role:str(uuid4()) for role in ROLES}
        session_token = secrets.token_urlsafe(32)
        with psycopg.connect(**{**params, "dbname":"protected_734"}) as admin:
            member = admin.execute("SELECT anggota_id,pengguna_bidx,nama_ct,email_ct,dek_pii_wrapped FROM anggota_protected WHERE legacy_row_id=1").fetchone()
            for role, identity in identities.items():
                admin.execute("INSERT INTO app_users(user_id,username,password_hash,role) VALUES(%s,%s,%s,%s)", (identity, role+".recovery", hashed, role))
                if role == "anggota": admin.execute("INSERT INTO service_member_bindings(user_id,pengguna_bidx) VALUES(%s,%s)", (identity, member[1]))
                if role in {"anggota", "operator", "privileged_officer", "finance_officer"}:
                    for permission in (["read"] if role == "finance_officer" else ["read","update"]):
                        admin.execute("INSERT INTO access_scope(principal,anggota_id,permission) VALUES(%s,%s,%s)", (identity,member[0],permission))
                if role == "privileged_officer": admin.execute("INSERT INTO access_scope(principal,permission) VALUES(%s,'insert')", (identity,))
            admin.execute("INSERT INTO service_sessions(token_hash,csrf_hash,user_id,expires_at) VALUES(%s,%s,%s,%s)",
                (hashlib.sha256(session_token.encode()).hexdigest(), hashlib.sha256(secrets.token_bytes(32)).hexdigest(), identities["privileged_officer"], utcnow()+timedelta(minutes=15)))
        with OpenBaoClient(token_env="OPENBAO_VALIDATION_TOKEN") as client:
            dek = client.unwrap("pii-kek", member[4])
            expected_name = decrypt(bytes(member[2]), dek, anggota_id=str(member[0]), column="nama")
            expected_email = decrypt(bytes(member[3]), dek, anggota_id=str(member[0]), column="email")
        with psycopg.connect(**lab["backup_params"]) as source:
            before = row_counts(source)
        checks["complete_seven_table_source"] = tuple(before) == SERVICE_TABLES and before["app_users"] == 6 and before["service_sessions"] == before["service_member_bindings"] == 1
        artifact = backup("protected_734",lab["backup_params"],lab["keys"],lab["store"],container=container)
        with monkeypatch.context() as patch:
            patch.delenv("OPENBAO_VALIDATION_TOKEN")
            without = restore(artifact["manifest"],params,lab["keys"],container=container)
        created.append(without["created_database"])
        checks["without_openbao_preserves_all_seven_tables"] = without["table_rows"] == before and not without["decryption_smoke"]["performed"]
        recovered = restore(artifact["manifest"],params,lab["keys"],container=container,with_openbao=True)
        created.append(recovered["created_database"])
        target = recovered["database"]
        checks["with_openbao_validates_data_controls_and_allocator"] = recovered["table_rows"] == before and recovered["service_schema_restored"] and all(recovered["security"].values())
        checks["ready_marker_published"] = recovered["created_database"]["marker"] == "dpr-service-restore-v1:"+artifact["artifact_id"]
        checks["restore_hba_rejects_plaintext"] = all(plaintext_rejected(params["host"], params["port"], target, role) for role in ("app_user","backup_user","bench_user","scanner_user"))
        settings = Settings(mode="protected", database_url=url("app_user",target), restored_database=target,
            analyst_database_url=url("analyst_user",target), auditor_database_url=url("auditor_user",target),
            openbao_addr=os.environ["OPENBAO_ADDR"], openbao_cacert=os.environ["OPENBAO_CACERT"], openbao_token=token)
        application = create_app(settings)
        with https_api(application,lab["root"]) as http:
            http.cookies.set("dpr_session",session_token)
            checks["existing_account_and_session_restored"] = http.get("/auth/me").status_code == 200
            def login(role):
                http.cookies.clear()
                assert http.get("/auth/csrf").status_code == 200
                headers = {"X-CSRF-Token":http.cookies.get("dpr_csrf", ""), "Origin":settings.app_origin}
                response = http.post("/auth/login",json={"username":role+".recovery","password":password},headers=headers)
                assert response.status_code == 200
                return {**headers,"X-CSRF-Token":http.cookies.get("dpr_csrf", "")}
            for role in ROLES:
                login(role)
                response = http.get("/anggota/1")
                checks["six_role_access:"+role] = response.status_code == (403 if role in {"analyst","auditor"} else 200)
                if role in {"analyst","auditor"}:
                    checks["restored_endpoint:"+role] = http.get("/analytics/summary" if role == "analyst" else "/audit").status_code == 200
                else:
                    checks["record_scope:"+role] = http.get("/anggota/2").status_code == 404 and http.get("/anggota").json()["total"] == 1
                    checks["finance_field_policy:"+role] = ("rekening" in response.json()) == (role == "finance_officer")
            headers = login("privileged_officer")
            checks["plaintext_matches_independent_A_decryption"] = http.get("/anggota/1").json().get("nama") == expected_name
            checks["restored_blind_lookup"] = http.get("/anggota/search",params={"email":expected_email}).json().get("total") == 1
            changed = "restored-"+uuid4().hex+"@example.invalid"
            response = http.patch("/anggota/1/kontak",json={"email":changed,"handphone":"081234567890"},headers=headers)
            checks["restored_contact_update"] = response.status_code == 200 and response.json().get("email") == changed
            checks["updated_blind_index"] = http.get("/anggota/search",params={"email":changed}).json().get("total") == 1 and http.get("/anggota/search",params={"email":expected_email}).json().get("total") == 0
            response = http.post("/anggota",json={"nama":"Anggota Pemulihan Sintetis","pengguna":"recovered-"+uuid4().hex},headers=headers)
            checks["restored_sequence_insert_and_creator_scope"] = response.status_code == 201 and response.json().get("anggota_id") == "18" and http.get("/anggota/18").status_code == 200
            with monkeypatch.context() as patch:
                patch.delenv("OPENBAO_TOKEN")
                response = http.get("/anggota/1")
                checks["missing_key_identity_fails_closed"] = response.status_code == 500 and response.json() == {"detail":"Operasi data gagal"}
            checks["capability_restored_after_reinjection"] = http.get("/anggota/1").status_code == 200
            checks["https_transport_verified"] = http.get("/auth/me").status_code == 200
        checks["seven_table_tamper_test"] = tamper_test(artifact["manifest"],params,lab["keys"],container=container)["passed"]
        checks["seven_table_retention_and_sequence"] = retention_test(artifact["manifest"],params,lab["backup_params"],lab["keys"],lab["store"],container=container)["passed"]
        with psycopg.connect(**lab["backup_params"]) as source:
            checks["source_rows_accounts_sessions_unchanged"] = row_counts(source) == before
        report.update(passed=all(checks.values()),backup_seconds=artifact["backup_seconds"],restore_seconds=recovered["restore_seconds"],size_bytes=artifact["size_bytes"],source_rows=17)
        assert report["passed"]
    finally:
        for identity in reversed(created): drop_created_database(params,identity)
        report["checked_at_utc"] = datetime.now(timezone.utc).isoformat()
        report["official_benchmark"] = False
        output = REPO/"evidence/backup/service-recovery-integration.json"
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
