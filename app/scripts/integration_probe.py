"""Real PostgreSQL 18/TLS/API probe using only a new disposable Compose project.

Never connects to postgres/baseline_100k/protected_* or an existing server. No
credential, record value, request body, ciphertext or Docker logs are exported.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(APP / "backend"))


def validated_project(value: str) -> str:
    if not re.fullmatch(r"dpr-b-probe-[0-9a-f]{12}", value):
        raise ValueError("Refusing non-disposable Docker project")
    return value


def validated_database(value: str) -> str:
    if not re.fullmatch(r"dpr_b_test_[0-9a-f]{12}", value):
        raise ValueError("Refusing non-disposable database")
    return value


def run_compose(command: list[str], env: dict[str, str], *arguments: str) -> str:
    result = subprocess.run(command + list(arguments), env=env, capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise RuntimeError("Disposable Compose command failed; output withheld")
    return result.stdout.strip()


def synthetic_row(number: int) -> dict[str, str | None]:
    """Invented local fixture; contains no organizer source values."""
    columns = "nama nama_lengkap nama_tanpa_gelar jenis_kelamin tempat_lahir tanggal_lahir tanggal_pernikahan no_ktp pekerjaan_terakhir alamat_jakarta telpon_jakarta alamat_daerah telpon_daerah handphone email ruangan status_kawin jumlah_anak jumlah_tanggungan jumlah_jiwa rekening nama_rekening npwp nama_kppn nip_kppn nama_bank kode_bank pengguna agama".split()
    row = {field: f"Uji {field} {number}" for field in columns}
    row.update(nama=f"Anggota Probe {number}", nama_lengkap=f"Anggota Probe {number}", nama_tanpa_gelar=f"Anggota Probe {number}",
               jenis_kelamin="L" if number % 2 else "P", tempat_lahir="Kota Uji", tanggal_lahir="1980-01-01",
               tanggal_pernikahan=None, no_ktp=f"3100000000{number:04d}", pekerjaan_terakhir="Penguji",
               alamat_jakarta="Alamat uji internal", alamat_daerah="Alamat uji daerah", telpon_jakarta="0210000001",
               telpon_daerah="0210000002", handphone=f"08{number:010d}", email=f"probe{number}@example.test",
               ruangan=f"UJI-{number}", status_kawin="TK", jumlah_anak="0", jumlah_tanggungan="0", jumlah_jiwa="1",
               rekening=f"900000000000{number:04d}", nama_rekening=f"Pemilik Uji {number}", npwp=f"70000000000{number:04d}",
               nama_kppn="KPPN Uji", nip_kppn=f"{number:018d}", nama_bank="Bank Uji", kode_bank=f"{number:03d}",
               pengguna=f"probe.member.{number}", agama="Agama Uji")
    return row


def postgres_ready(owner_url, timeout: float = 90):
    from sqlalchemy import create_engine, text
    deadline = time.monotonic() + timeout
    engine = create_engine(owner_url, hide_parameters=True, connect_args={"connect_timeout": 2})
    while True:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return engine
        except Exception:
            if time.monotonic() >= deadline:
                engine.dispose()
                raise RuntimeError("Disposable PostgreSQL TLS readiness timed out") from None
            time.sleep(.5)


def prepare_database(owner_engine, passwords, rows):
    from sqlalchemy import BigInteger, Column, Date, Identity, MetaData, SmallInteger, Table, Text, text
    from sqlalchemy.orm import Session as SQLSession
    from psycopg import sql
    from argon2 import PasswordHasher
    from service_app.models import Base, User, Session, AuditLog, SOURCE_FIELDS

    # Service models own only this fresh test database. View metadata is a
    # lightweight table descriptor in SQLite tests; PostgreSQL gets a real view.
    Base.metadata.create_all(owner_engine, tables=[table for table in Base.metadata.sorted_tables if table.name not in {"analyst_view", "anggota"}])
    # Match the team's native date/integer baseline types instead of only
    # testing the SQLite-friendly descriptors used by the query repository.
    typed = MetaData()
    dates = {"tanggal_lahir", "tanggal_pernikahan"}
    counts = {"jumlah_anak", "jumlah_tanggungan", "jumlah_jiwa"}
    table = Table("anggota", typed, Column("id", BigInteger, Identity(always=True), primary_key=True),
                  *(Column(field, Date if field in dates else SmallInteger if field in counts else Text, nullable=field != "nama") for field in SOURCE_FIELDS))
    typed.create_all(owner_engine)
    values = [{field: date.fromisoformat(value) if field in dates and value is not None else int(value) if field in counts and value is not None else value
               for field, value in row.items()} for row in rows]
    with owner_engine.begin() as connection:
        connection.execute(table.insert(), values)
        connection.execute(text("CREATE VIEW analyst_view WITH (security_barrier=true) AS SELECT jenis_kelamin, pekerjaan_terakhir, nama_kppn, nama_bank, '40-49'::text AS age_band FROM anggota"))
    # Every account password is generated at runtime and never printed.
    hasher = PasswordHasher()
    accounts = {}
    with SQLSession(owner_engine) as session:
        for role in ["operator", "privileged_officer", "finance_officer", "analyst", "auditor", "anggota"]:
            password = secrets.token_urlsafe(24)
            username = f"probe.{role}"
            principal = rows[0]["pengguna"] if role == "anggota" else username
            session.add(User(id=str(uuid.uuid4()), username=username, password_hash=hasher.hash(password), role=role, principal=principal, active=True))
            accounts[role] = {"username": username, "password": password}
        session.commit()
    raw = owner_engine.raw_connection()
    try:
        with raw.cursor() as cursor:
            for role, password in passwords.items():
                cursor.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS").format(sql.Identifier(role), sql.Literal(password)))
            cursor.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
            cursor.execute("GRANT USAGE ON SCHEMA public TO app_user, analyst_user, auditor_user")
            cursor.execute("GRANT SELECT, INSERT, UPDATE ON anggota TO app_user")
            cursor.execute("GRANT USAGE, SELECT ON SEQUENCE anggota_id_seq, audit_log_id_seq TO app_user")
            cursor.execute(sql.SQL("GRANT SELECT, UPDATE ON {} TO app_user").format(sql.Identifier(User.__table__.name)))
            cursor.execute(sql.SQL("GRANT SELECT, INSERT, DELETE ON {} TO app_user").format(sql.Identifier(Session.__table__.name)))
            cursor.execute(sql.SQL("GRANT SELECT, INSERT ON {} TO app_user").format(sql.Identifier(AuditLog.__table__.name)))
            cursor.execute(sql.SQL("GRANT SELECT ON {} TO auditor_user").format(sql.Identifier(AuditLog.__table__.name)))
            cursor.execute("GRANT SELECT ON analyst_view TO analyst_user")
            cursor.execute("ALTER TABLE anggota ENABLE ROW LEVEL SECURITY")
            cursor.execute("ALTER TABLE anggota FORCE ROW LEVEL SECURITY")
            cursor.execute("CREATE POLICY probe_object_scope ON anggota TO app_user USING (current_setting('app.role',true) IS DISTINCT FROM 'anggota' OR pengguna=current_setting('app.principal',true)) WITH CHECK (current_setting('app.role',true) IS DISTINCT FROM 'anggota' OR pengguna=current_setting('app.principal',true))")
        raw.commit()
    finally:
        raw.close()
    return accounts


def check_database_roles(urls, checks, principal_value):
    from sqlalchemy import create_engine, text
    for role, url in urls.items():
        engine = create_engine(url, hide_parameters=True)
        try:
            with engine.connect() as connection:
                current = connection.execute(text("SELECT current_user")).scalar_one()
                tls = connection.execute(text("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()")).scalar_one()
                checks[f"identity:{role}"] = current == role
                checks[f"tls:{role}"] = bool(tls)
                flags = connection.execute(text("SELECT rolsuper,rolcreatedb,rolcreaterole,rolbypassrls FROM pg_roles WHERE rolname=current_user")).one()
                checks[f"least_privilege_flags:{role}"] = not any(flags)
                checks[f"no_ddl:{role}"] = not connection.execute(text("SELECT has_schema_privilege(current_user,'public','CREATE')")).scalar_one()
                if role in {"analyst_user", "auditor_user"}:
                    checks[f"base_table_denied:{role}"] = not connection.execute(text("SELECT has_table_privilege(current_user,'anggota','SELECT')")).scalar_one()
            if role == "app_user":
                with engine.begin() as connection:
                    connection.execute(text("SELECT set_config('app.role','anggota',true), set_config('app.principal',:principal,true)"), {"principal": principal_value})
                    checks["forced_rls_member_scope"] = connection.execute(text("SELECT count(*) FROM anggota")).scalar_one() == 1
                    checks["forced_rls_enabled"] = all(connection.execute(text("SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid='anggota'::regclass")).one())
                with engine.connect() as connection:
                    checks["principal_resets_after_transaction"] = connection.execute(text("SELECT current_setting('app.principal',true)")).scalar_one() in {None, ""}
        finally:
            engine.dispose()


def exercise_api(settings, accounts, rows, checks):
    from fastapi.testclient import TestClient
    from sqlalchemy import event
    from service_app.main import create_app
    app = create_app(settings)
    observed = {"set_local": False}
    def observe_statement(connection, cursor, statement, parameters, context, executemany):
        if "set_config('app.principal'" in statement and "set_config('app.role'" in statement:
            observed["set_local"] = True
    event.listen(app.state.engine, "before_cursor_execute", observe_statement)
    with TestClient(app, base_url="https://localhost:3443") as client:
        checks["unauthenticated_denied"] = client.get("/anggota").status_code == 401
        for role, account in accounts.items():
            client.cookies.clear()
            client.get("/auth/csrf")
            csrf = {"X-CSRF-Token": client.cookies.get("dpr_csrf", ""), "Origin": settings.app_origin}
            response = client.post("/auth/login", json=account, headers=csrf)
            checks[f"login:{role}"] = response.status_code == 200
            session_header = next((v for v in response.headers.get_list("set-cookie") if v.startswith("dpr_session=")), "")
            checks[f"cookie:{role}"] = all(flag in session_header for flag in ["HttpOnly", "Secure", "SameSite=strict"])
            if response.status_code != 200:
                continue
            csrf = {"X-CSRF-Token": client.cookies.get("dpr_csrf", ""), "Origin": settings.app_origin}
            detail = client.get("/anggota/1")
            if role in {"analyst", "auditor"}:
                checks[f"record_denied:{role}"] = detail.status_code == 403
                checks[f"list_denied:{role}"] = client.get("/anggota").status_code == 403
                endpoint = "/analytics/summary" if role == "analyst" else "/audit"
                checks[f"own_endpoint:{role}"] = client.get(endpoint).status_code == 200
                other = "/audit" if role == "analyst" else "/analytics/summary"
                checks[f"other_endpoint_denied:{role}"] = client.get(other).status_code == 403
                continue
            checks[f"detail:{role}"] = detail.status_code == 200
            if detail.status_code != 200:
                continue
            raw = detail.json()
            checks[f"finance_allowlist:{role}"] = ("rekening" in raw) if role == "finance_officer" else not any(field in raw for field in ["rekening", "nama_rekening", "npwp", "kode_bank"])
            if role in {"operator", "finance_officer"}:
                checks[f"ktp_masked:{role}"] = rows[0]["no_ktp"] not in detail.text
            listed = client.get("/anggota")
            checks[f"list:{role}"] = listed.status_code == 200 and listed.json()["page_size"] == 50
            if role in {"operator", "finance_officer"}:
                checks[f"name_masked:{role}"] = rows[0]["nama"] not in listed.text
            if role == "anggota":
                checks["member_self_only"] = listed.json()["total"] == 1
                checks["idor_detail_denied"] = client.get("/anggota/2").status_code == 404
                checks["idor_patch_denied"] = client.patch("/anggota/2/kontak", json={"email": "denied@example.test"}, headers=csrf).status_code == 404
                checks["idor_search_empty"] = client.get("/anggota/search", params={"email": rows[1]["email"]}).json()["total"] == 0
            if role == "operator":
                injected = client.get("/anggota/search", params={"email": "' OR 1=1 --"})
                checks["injection_no_records"] = injected.status_code in {200, 422} and (injected.status_code == 422 or injected.json()["total"] == 0)
                checks["csrf_patch_denied"] = client.patch("/anggota/1/kontak", json={"email": "new@example.test"}).status_code == 403
                checks["contact_update"] = client.patch("/anggota/1/kontak", json={"email": "probe.updated@example.test"}, headers=csrf).status_code == 200
                checks["headers"] = (detail.headers.get("cache-control") == "no-store" and detail.headers.get("x-content-type-options") == "nosniff" and detail.headers.get("referrer-policy") == "no-referrer")
            if role == "privileged_officer":
                checks["insert"] = client.post("/anggota", json=synthetic_row(4), headers=csrf).status_code == 201
            checks[f"logout:{role}"] = client.post("/auth/logout", headers=csrf).status_code == 200
    checks["api_sets_transaction_principal"] = observed["set_local"]
    for name in ["engine", "auth_engine"]:
        engine = getattr(app.state, name, None)
        if engine is not None:
            engine.dispose()


def free_loopback_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def stop_owned_process(process):
    # Popen keeps the process handle; poll(None) means this exact owned parent
    # still lives. Windows venv launchers can have child interpreters, so stop
    # only this recorded process tree rather than matching global process names.
    if process is None or process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=True)
    else:
        process.terminate()
    process.wait(timeout=15)


def wait_https(url, ca_file, process, timeout=75):
    import httpx
    deadline = time.monotonic() + timeout
    context = ssl.create_default_context(cafile=str(ca_file))
    with httpx.Client(verify=context, trust_env=False, timeout=2) as client:
        while True:
            if process.poll() is not None:
                raise RuntimeError("Owned HTTPS server exited before readiness")
            try:
                response = client.get(url)
                if response.status_code == 200:
                    return True
            except httpx.HTTPError:
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError("Owned HTTPS server readiness timed out")
            time.sleep(.5)


def exercise_live_https(settings, accounts, private, checks):
    """Real browser -> Next HTTPS -> verified API HTTPS -> PostgreSQL TLS."""
    node = shutil.which("node")
    if not node or not (APP / "web/.next/BUILD_ID").is_file() or not (APP / "web/scripts/live-probe.mjs").is_file():
        raise RuntimeError("Build app/web and install its Chromium dependencies before live HTTPS probe")
    web_port, api_port = free_loopback_port(), free_loopback_port()
    while web_port == api_port:
        api_port = free_loopback_port()
    base_url = f"https://localhost:{web_port}"
    ca = private / "tls/ca.crt"
    # The plain service needs only its runtime DB identities. Never inherit
    # setup/migration/root/OpenBao credentials into either web process.
    base_env = {k: v for k, v in os.environ.items() if not any(word in k.upper() for word in ["DATABASE_URL", "PASSWORD", "TOKEN", "SECRET", "PRIVATE_DIR"])}
    api_env = {**base_env, "MODE": "plain", "DATABASE_URL": settings.database_url,
               "AUTH_DATABASE_URL": settings.auth_database_url,
               "ANALYST_DATABASE_URL": settings.analyst_database_url,
               "AUDITOR_DATABASE_URL": settings.auditor_database_url,
               "DPR_ALLOW_DISPOSABLE_DATABASE": "1", "APP_ORIGIN": base_url,
               "SESSION_TTL_SECONDS": "900", "API_PORT": str(api_port),
               "TLS_CERT_FILE": str(private / "tls/server.crt"), "TLS_KEY_FILE": str(private / "tls/server.key")}
    web_env = {**base_env, "APP_ORIGIN": base_url, "WEB_PORT": str(web_port), "WEB_HOST": "127.0.0.1",
               "API_INTERNAL_URL": f"https://127.0.0.1:{api_port}", "NODE_EXTRA_CA_CERTS": str(ca),
               "NODE_ENV": "production", "NEXT_TELEMETRY_DISABLED": "1",
               "TLS_CERT_FILE": str(private / "tls/server.crt"), "TLS_KEY_FILE": str(private / "tls/server.key")}
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    api_process = web_process = browser_process = None
    try:
        api_process = subprocess.Popen([sys.executable, str(APP / "scripts/serve.py")], cwd=ROOT, env=api_env,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **flags)
        checks["live_api_https_verified_ca"] = wait_https(f"https://127.0.0.1:{api_port}/health/ready", ca, api_process)
        web_process = subprocess.Popen([node, "server.mjs"], cwd=APP / "web", env=web_env,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **flags)
        checks["live_web_https_verified_ca"] = wait_https(base_url + "/login", ca, web_process)
        from cryptography import x509
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        certificate = x509.load_pem_x509_certificate((private / "tls/server.crt").read_bytes())
        spki = base64.b64encode(hashlib.sha256(certificate.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)).digest()).decode()
        # Browser passwords go through stdin only; no secrets are shell args,
        # files, traces, screenshots or printed output.
        browser_process = subprocess.Popen([node, "scripts/live-probe.mjs"], cwd=APP / "web", env=web_env,
                                           stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, **flags)
        stdout, _ = browser_process.communicate(json.dumps({"baseURL": base_url, "accounts": accounts, "spki": spki}), timeout=180)
        result = json.loads(stdout)
        observed = result.get("checks", {})
        if not isinstance(observed, dict) or not all(isinstance(v, bool) for v in observed.values()):
            raise RuntimeError("Browser probe returned unsupported evidence format")
        checks.update({"browser:" + str(name): value for name, value in observed.items()})
        checks["live_browser_probe_passed"] = browser_process.returncode == 0 and result.get("status") == "PASSED"
    finally:
        for process in [browser_process, web_process, api_process]:
            stop_owned_process(process)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=APP / "evidence/access-control/postgres-tls.json")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(APP):
        raise ValueError("Evidence must stay in app/ for this module task")
    project = validated_project("dpr-b-probe-" + secrets.token_hex(6))
    database = validated_database("dpr_b_test_" + secrets.token_hex(6))
    command = ["docker", "compose", "-p", project, "-f", str(APP / "scripts/integration.compose.yaml")]
    collision = subprocess.run(["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={project}"], capture_output=True, text=True, check=True)
    if collision.stdout.strip():
        raise RuntimeError("Unexpected project collision; refusing to use existing resources")
    from infra.tls.make_ca import make_ca
    from infra.security import secure_directory
    from sqlalchemy import create_engine
    from sqlalchemy.engine import URL
    from service_app.config import Settings
    checks = {}
    report = {"schema_version": 1, "status": "NOT TESTED", "scope": "new disposable PostgreSQL 18 database + verified TLS; FastAPI ASGI requests; no source/baseline/team database accessed", "checks": checks,
              "protected_live": "NOT TESTED: Module A toolkit/profile/test vectors unavailable", "browser_https": "NOT TESTED", "source_database_accessed": False}
    created = False
    owner_engine = None
    with tempfile.TemporaryDirectory(prefix="dpr-b-tls-") as temporary:
        private = secure_directory(Path(temporary) / "private")
        make_ca(private / "tls")
        make_ca(private / "wrong-ca")
        env = {**os.environ, "DPR_B_PROBE_DATABASE": database,
               "DPR_B_PROBE_ADMIN_PASSWORD": secrets.token_urlsafe(32), "DPR_B_PROBE_TLS": str(private / "tls")}
        passwords = {role: secrets.token_urlsafe(32) for role in ["app_user", "analyst_user", "auditor_user"]}
        try:
            created = True
            run_compose(command, env, "up", "-d", "postgres")
            port = int(run_compose(command, env, "port", "postgres", "5432").rsplit(":", 1)[1])
            query = {"sslmode": "verify-full", "sslrootcert": str(private / "tls/ca.crt")}
            owner_url = URL.create("postgresql+psycopg", username="probe_owner", password=env["DPR_B_PROBE_ADMIN_PASSWORD"], host="127.0.0.1", port=port, database=database, query=query)
            owner_engine = postgres_ready(owner_url)
            from sqlalchemy import text
            with owner_engine.connect() as connection:
                version = int(connection.execute(text("SHOW server_version_num")).scalar_one())
                checks["postgres_18"] = 180000 <= version < 190000
                report["postgres_server_version_num"] = version
            wrong = create_engine(owner_url.update_query_dict({"sslrootcert": str(private / "wrong-ca/ca.crt")}), hide_parameters=True, connect_args={"connect_timeout": 3})
            try:
                with wrong.connect():
                    checks["wrong_ca_rejected"] = False
            except Exception:
                checks["wrong_ca_rejected"] = True
            finally:
                wrong.dispose()
            rows = [synthetic_row(i) for i in range(1, 4)]
            accounts = prepare_database(owner_engine, passwords, rows)
            urls = {role: owner_url.set(username=role, password=password) for role, password in passwords.items()}
            check_database_roles(urls, checks, rows[0]["pengguna"])
            settings = Settings(mode="plain", database_url=urls["app_user"].render_as_string(hide_password=False),
                                auth_database_url=urls["app_user"].render_as_string(hide_password=False),
                                analyst_database_url=urls["analyst_user"].render_as_string(hide_password=False),
                                auditor_database_url=urls["auditor_user"].render_as_string(hide_password=False),
                                app_origin="https://localhost:3443", testing=False, allow_disposable_database=True)
            exercise_api(settings, accounts, rows, checks)
            exercise_live_https(settings, accounts, private, checks)
            report["browser_https"] = "TESTED: real Next HTTPS/API HTTPS with verified local CA and browser certificate SPKI pin, six roles; no global TLS verification bypass"
            report["status"] = "PASSED" if checks and all(checks.values()) else "FAILED"
        except Exception as exc:
            report["status"] = "FAILED"
            report["failure_class"] = type(exc).__name__
        finally:
            if owner_engine is not None:
                owner_engine.dispose()
            if created:
                try:
                    # The name was validated and proven absent before this run.
                    run_compose(command, env, "down", "--volumes", "--remove-orphans")
                    report["cleanup_passed"] = True
                except Exception:
                    report["cleanup_passed"] = False
                    report["status"] = "FAILED"
                    # Retain only the random project name for explicit cleanup, no secrets.
                    report["cleanup_project"] = project
            report["checked_at_utc"] = datetime.now(timezone.utc).isoformat()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": len(checks), "failed_checks": [k for k, v in checks.items() if not v], "cleanup_passed": report.get("cleanup_passed", False)}))
    return 0 if report["status"] == "PASSED" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"status": "FAILED", "failure_class": type(exc).__name__, "details": "withheld to avoid secret or data exposure"}))
        raise SystemExit(1) from None
