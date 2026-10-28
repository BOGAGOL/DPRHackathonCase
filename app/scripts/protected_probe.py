"""B integration against A's unmodified schema/toolkit, real PG18 and TLS OpenBao.

Creates only random disposable containers with invented rows. No pg-dpr, source
dataset, existing keys, migration runs or benchmark resources are modified.
"""
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app"
sys.path[:0] = [str(ROOT), str(APP / "backend"), str(APP / "scripts")]


def main():
    import psycopg
    from sqlalchemy import create_engine, select
    from sqlalchemy.engine import URL
    from fastapi.testclient import TestClient
    from dprcrypto import OpenBaoClient, KeyManager, BlindIndexer, encrypt
    from infra.security import secure_directory
    from infra.tls.make_ca import make_ca
    from infra.postgres.make_cert import make_certificate
    from infra.postgres.enable_tls import ExistingPostgres, TLSUpdateError
    from infra.protected.apply import provision, load_profile
    from infra.protected.credentials import ROLES
    from infra.openbao.api import BaoAPI, BaoError
    from infra.openbao.init import initialize, unseal, configure, issue_tokens
    from service_app.config import Settings
    from service_app.main import create_app
    from service_app.models import protected_members, FIN, REF
    from service_app.protected_control import ProtectedUser
    from schema import setup_protected
    from integration_probe import synthetic_row, exercise_live_https
    from uuid import uuid4
    from sqlalchemy.orm import Session

    report = {"status": "FAILED", "scope": "invented rows; actual Module A schema/toolkit, PG18 + OpenBao TLS, protected API and real HTTPS browser; not local migrated datasets or official benchmark", "checks": {}}
    checks = report["checks"]
    def check(name, value):
        checks[name] = bool(value)
        if not value:
            raise RuntimeError("Integration assertion failed")
    project = "dpr-b-protected-" + secrets.token_hex(6)
    command = ["docker", "compose", "-p", project, "-f", str(ROOT / "infra/compose.yaml"), "-f", str(ROOT / "infra/tests/compose.postgres.yaml")]
    app = engine = None
    original_env = os.environ.copy()
    with tempfile.TemporaryDirectory(prefix="dpr-b-protected-") as temp:
        private = secure_directory(Path(temp) / "private")
        make_ca(private / "tls")
        make_certificate(private)
        admin_password = secrets.token_urlsafe(32)
        env = {**os.environ, "DPR_SECRETS_DIR": str(private), "DPR_POSTGRES_PORT": "0", "DPR_OPENBAO_PORT": "0", "DPR_POSTGRES_PASSWORD": admin_password}
        def compose(*args):
            result = subprocess.run(command + list(args), env=env, capture_output=True, text=True, timeout=180)
            if result.returncode:
                raise RuntimeError("Disposable Compose failed; output withheld")
            return result.stdout.strip()
        created = False
        try:
            collision = subprocess.run(["docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=" + project], capture_output=True, text=True, check=True)
            if collision.stdout.strip():
                raise RuntimeError("Unexpected disposable project collision")
            created = True
            compose("up", "-d")
            port = int(compose("port", "postgres", "5432").rsplit(":", 1)[1])
            address = "https://127.0.0.1:" + compose("port", "openbao", "8200").rsplit(":", 1)[1]
            pg = ExistingPostgres(project + "-postgres-1", port=port)
            for _ in range(100):
                try:
                    pg.metadata()
                    break
                except TLSUpdateError:
                    time.sleep(.5)
            else:
                raise RuntimeError("Disposable PG18 startup timed out")
            params = dict(host="127.0.0.1", port=port, user="dpr_bootstrap", password=admin_password, dbname="postgres", autocommit=True)
            with psycopg.connect(**params) as db:
                db.execute("CREATE DATABASE protected_734")
            pg.apply(private)
            params.update(dbname="protected_734", sslmode="verify-full", sslrootcert=str(private / "postgres/tls/ca.crt"))
            passwords = {role: secrets.token_urlsafe(32) for role in ROLES}
            provision(project + "-postgres-1", "protected_734", "dpr_bootstrap", passwords, load_profile(ROOT / "policy/protection_profile.yaml"))
            bao = BaoAPI(address, str(private / "tls/ca.crt"))
            for _ in range(100):
                try:
                    bao.request("/sys/seal-status")
                    break
                except BaoError:
                    time.sleep(.5)
            else:
                raise RuntimeError("Disposable OpenBao startup timed out")
            initialize(bao, private)
            material = json.loads((private / "openbao/init-material.json").read_text())
            for share in material["keys_base64"][:2]:
                unseal(bao, share)
            configure(bao, material["root_token"])
            issue_tokens(bao, material["root_token"], private, 3600)
            token = json.loads(next((private / "openbao/tokens").glob("svc-app-*.json")).read_text())["auth"]["client_token"]
            os.environ.update(OPENBAO_ADDR=address, OPENBAO_CACERT=str(private / "tls/ca.crt"), OPENBAO_TOKEN=token)
            def url(role, password):
                return URL.create("postgresql+psycopg", username=role, password=password, host="127.0.0.1", port=port,
                    database="protected_734", query={"sslmode": "verify-full", "sslrootcert": params["sslrootcert"]})
            owner = url("dpr_bootstrap", admin_password)
            engine = create_engine(owner, hide_parameters=True)
            original = [synthetic_row(i) for i in range(1, 9)]
            # Encryption producer is Module A's public API, independent of B's bridge.
            with OpenBaoClient() as client, KeyManager(client, cache_ttl=0) as keys, engine.begin() as db:
                for i, row in enumerate(original, 1):
                    row.update(pekerjaan_terakhir="Dokter" if i == 1 else "Guru", nama_kppn="KPPN Surabaya")
                    uid, record = str(uuid4()), keys.create_record_keys()
                    values = dict(anggota_id=uid, legacy_row_id=i, protection_version=1,
                                  dek_pii_wrapped=record.pii.wrapped, dek_fin_wrapped=record.finance.wrapped, age_band="40-49")
                    for field, value in row.items():
                        values[field if field in REF else field + "_ct"] = value if field in REF else encrypt(value, record.finance.dek if field in FIN else record.pii.dek, column=field, anggota_id=uid)
                    for field in ("pengguna", "no_ktp", "email"):
                        values[field + "_bidx"] = BlindIndexer(client).digest(field, row[field])
                    db.execute(protected_members.insert().values(**values))
            setup_protected(engine)
            setup_protected(engine)
            settings = Settings(mode="protected", database_url=url("app_user", passwords["app_user"]).render_as_string(hide_password=False),
                analyst_database_url=url("analyst_user", passwords["analyst_user"]).render_as_string(hide_password=False),
                auditor_database_url=url("auditor_user", passwords["auditor_user"]).render_as_string(hide_password=False),
                openbao_addr=address, openbao_cacert=str(private / "tls/ca.crt"), openbao_token=token)
            os.environ.update(MODE="protected", DATABASE_URL=settings.database_url, ANALYST_DATABASE_URL=settings.analyst_database_url,
                AUDITOR_DATABASE_URL=settings.auditor_database_url, DPR_PRIVATE_DIR=str(private),
                APP_SETUP_DATABASE_URL=owner.render_as_string(hide_password=False), DEMO_MEMBER_PRINCIPAL=original[0]["pengguna"], DEMO_ASSIGNED_IDS="1,2")
            result = subprocess.run([sys.executable, str(APP / "scripts/provision.py")], cwd=ROOT, env=os.environ.copy(), capture_output=True, text=True)
            check("B_provisioning_with_A_schema", result.returncode == 0)
            accounts = {a["role"]: {"username": a["username"], "password": a["password"]} for a in json.loads((private / "service-b/service-b-protected-accounts.json").read_text())}
            with Session(engine) as db:
                ids = {u.role: u.id for u in db.scalars(select(ProtectedUser))}
            with psycopg.connect(**params) as db:
                check("A_schema_owner_preserved", db.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tableowner<>'schema_owner'").fetchone()[0] == 0)
                check("A_audit_no_extra_grants", not db.execute("SELECT has_column_privilege('app_user','audit_log','actor','INSERT')").fetchone()[0])
            app = create_app(settings)
            with TestClient(app, base_url=settings.app_origin, raise_server_exceptions=False) as http:
                def login(role):
                    http.cookies.clear()
                    http.get("/auth/csrf")
                    headers = {"X-CSRF-Token": http.cookies.get("dpr_csrf", ""), "Origin": settings.app_origin}
                    check("login:" + role, http.post("/auth/login", json=accounts[role], headers=headers).status_code == 200)
                    return {**headers, "X-CSRF-Token": http.cookies.get("dpr_csrf", "")}
                for role in accounts:
                    headers = login(role)
                    detail = http.get("/anggota/1")
                    if role in {"analyst", "auditor"}:
                        check("record_denied:" + role, detail.status_code == 403)
                        endpoint = "/analytics/summary" if role == "analyst" else "/audit"
                        response = http.get(endpoint)
                        check("own_endpoint:" + role, response.status_code == 200)
                        if role == "analyst":
                            filtered = http.get(endpoint, params={"nama_kppn": "KPPN Surabaya", "pekerjaan_terakhir": "Dokter"})
                            check("cohort_filter_rejected", filtered.status_code == 422)
                            groups = response.json().get("groups", [])
                            check("A5_total_unavailable", response.json().get("total") is None)
                            check("B4_small_label_omitted", not any(g["value"] == "Dokter" for g in groups))
                            check("A5_threshold", all(isinstance(g["count"], int) and g["count"] >= 5 for g in groups))
                            check("A5_released_group", any(g["dimension"] == "pekerjaan_terakhir" and g["value"] == "Guru" and g["count"] == 7 for g in groups))
                        continue
                    check("detail:" + role, detail.status_code == 200)
                    expected = 1 if role == "anggota" else 2
                    check("assigned_rows_only:" + role, http.get("/anggota").json().get("total") == expected)
                    check("unassigned_staff_IDOR:" + role, http.get("/anggota/3").status_code == 404)
                    check("fields:" + role, ("rekening" in detail.json()) == (role == "finance_officer"))
                    check("lookup:" + role, http.get("/anggota/search", params={"email": original[0]["email"]}).json().get("total") == 1)
                headers = login("privileged_officer")
                check("A_ciphertext_decrypts_in_B", http.get("/anggota/1").json().get("nama") == original[0]["nama"])
                created_response = http.post("/anggota", headers=headers, json=synthetic_row(20))
                check("scoped_insert_no_RETURNING", created_response.status_code == 201 and created_response.json().get("anggota_id") == "9")
                check("new_record_scope_trigger", http.get("/anggota/9").status_code == 200)
                changed = http.patch("/anggota/1/kontak", headers=headers, json={"email": "changed@example.test"})
                check("reencrypt_and_bidx_update", changed.status_code == 200 and http.get("/anggota/search", params={"email": "changed@example.test"}).json().get("total") == 1)
                http.patch("/anggota/1/kontak", headers=headers, json={"email": original[0]["email"]})
                with psycopg.connect(**params) as db:
                    ciphertext = db.execute("SELECT nama_ct FROM anggota_protected WHERE legacy_row_id=1").fetchone()[0]
                    db.execute("UPDATE anggota_protected SET nama_ct=(SELECT nama_ct FROM anggota_protected WHERE legacy_row_id=2) WHERE legacy_row_id=1")
                failed = http.get("/anggota/1")
                check("real_AAD_swap_generic_500", failed.status_code == 500 and failed.json() == {"detail": "Operasi data gagal"})
                with psycopg.connect(**params) as db:
                    db.execute("UPDATE anggota_protected SET nama_ct=%s WHERE legacy_row_id=1", (ciphertext,))
                    check("A_audit_context_and_error", db.execute("SELECT count(*) FROM audit_log WHERE actor=%s AND actor_role='privileged_officer' AND action='decrypt' AND decision='error' AND anggota_id IS NOT NULL", (ids["privileged_officer"],)).fetchone()[0] > 0)
                exercise_live_https(settings, accounts, private, checks)
                # Real revoked token + cache disabled must fail, never use prior DEKs/plaintext.
                bao.request("/auth/token/revoke", token=material["root_token"], payload={"token": token})
                failed = http.get("/anggota/1")
                check("revoked_key_identity_fails_closed", failed.status_code == 500 and failed.json() == {"detail": "Operasi data gagal"})
            report["status"] = "PASSED"
        except Exception as exc:
            report["failure_class"] = type(exc).__name__
        finally:
            if engine:
                engine.dispose()
            if created:
                try:
                    compose("down", "--volumes", "--remove-orphans")
                    report["cleanup_passed"] = True
                except Exception:
                    report.update(status="FAILED", cleanup_passed=False, cleanup_project=project)
            os.environ.clear()
            os.environ.update(original_env)
            report["checked_at_utc"] = datetime.now(timezone.utc).isoformat()
            target = APP / "evidence/access-control/protected-integration.json"
            target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": len(checks), "failed_checks": [k for k, v in checks.items() if not v], "failure_class": report.get("failure_class"), "cleanup_passed": report.get("cleanup_passed")}))
    return 0 if report["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
