"""Persistent, explicitly owned Zhafif lab; no changes to A/C source files.

Only a NEW pg-dpr instance may bootstrap postgres from the team's private dataset.
After that source reads are READ ONLY. Existing unrelated instances are refused.
No credentials/rows/driver messages are printed. Secrets stay outside the checkout.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app"
sys.path[:0] = [str(ROOT), str(APP / "backend"), str(APP / "scripts")]
ROLES = ("app_user", "analyst_user", "auditor_user", "bench_user", "scanner_user")
OWNER = "service-b-local"


def command(arguments, *, env=None, input=None):
    result = subprocess.run(arguments, cwd=ROOT, env=env, input=input,
                            capture_output=True, text=True, encoding="utf-8", timeout=240)
    if result.returncode:
        raise RuntimeError("Local lab command failed; output withheld")
    return result.stdout


def inspect_owned():
    result = subprocess.run(["docker", "container", "inspect", "pg-dpr"],
                            capture_output=True, text=True, timeout=15)
    if result.returncode:
        # Distinguish no such container from an inaccessible daemon.
        command(["docker", "info", "--format", "{{.ServerVersion}}"])
        if "No such" not in result.stderr:
            raise RuntimeError("Cannot safely inspect pg-dpr")
        return None
    value = json.loads(result.stdout)[0]
    labels = value.get("Config", {}).get("Labels", {})
    if labels.get("dpr.owner") != OWNER or labels.get("com.docker.compose.project") != "dpr-zhafif-local":
        raise ValueError("Existing pg-dpr is not owned by this lab; refusing changes")
    return value


def private_directory():
    from infra.security import external_directory
    default = str(Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "DPR/zhafif-local")
    return external_directory(os.environ.get("DPR_B_LAB_DIR", default))


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_state(directory):
    state = json.loads((directory / "state.json").read_text(encoding="utf-8"))
    if state.get("owner") != OWNER or set(state.get("passwords", {})) != {"postgres", *ROLES}:
        raise ValueError("Unexpected local lab state")
    return state


def db_url(directory, state, role, database="baseline_100k", driver="postgresql+psycopg"):
    from sqlalchemy.engine import URL
    if role not in {"postgres", *ROLES} or database not in {"postgres", "baseline_100k"}:
        raise ValueError("Unexpected local lab identity or target")
    return URL.create(driver, username=role, password=state["passwords"][role], host="127.0.0.1",
                      port=5433, database=database,
                      query={"sslmode": "verify-full", "sslrootcert": str(directory / "runtime/tls/ca.crt")})


def compose(directory):
    env = {**os.environ, "DPR_B_LAB_RUNTIME": str(directory / "runtime")}
    command(["docker", "compose", "-p", "dpr-zhafif-local", "-f",
             str(APP / "scripts/local-lab.compose.yaml"), "up", "-d", "postgres"], env=env)


def source_payload(ref):
    # Dataset goes straight from Git into memory; never print/copy into evidence or fixtures.
    import re
    if not re.fullmatch(r"(?:origin/main|[0-9a-f]{40})", ref):
        raise ValueError("Use origin/main or an exact reviewed dataset commit")
    commit = command(["git", "rev-parse", ref]).strip()
    data = command(["git", "show", commit + ":sql/baseline/02_data.sql"])
    if len(re.findall(r"\bINSERT\s+INTO\b", data, re.I)) != 734:
        raise ValueError("Expected the team's 734 INSERT statements")
    return commit, data


def setup(directory, ref):
    from infra.security import secure_directory, write_private
    from infra.tls.make_ca import make_ca
    from integration_probe import postgres_ready
    from sqlalchemy import text
    import psycopg
    from psycopg import sql
    from datagen import database as generator
    from datagen.model import checksum

    existing = inspect_owned()
    state_file = directory / "state.json"
    if not state_file.exists():
        if existing is not None:
            raise ValueError("Cannot adopt an existing container without its original private state")
        # Refuse an orphan volume: no new credentials may be applied to old storage.
        volume = command(["docker", "volume", "ls", "-q", "--filter", "label=com.docker.compose.project=dpr-zhafif-local"])
        if volume.strip():
            raise ValueError("Existing lab volume without custody state; manual recovery required")
        secure_directory(directory)
        runtime = secure_directory(directory / "runtime")
        make_ca(runtime / "tls")
        state = {"owner": OWNER, "passwords": {role: secrets.token_urlsafe(32) for role in ("postgres", *ROLES)},
                 "source_initialized": False}
        write_private(runtime / "admin-password", state["passwords"]["postgres"].encode())
        # Only server material is mounted; CA private key remains outside the container.
        custody = secure_directory(directory / "custody")
        (runtime / "tls/ca.key").replace(custody / "ca.key")
        save(state_file, state)
    else:
        state = load_state(directory)
    compose(directory)
    inspect_owned()
    engine = postgres_ready(db_url(directory, state, "postgres", "postgres"))
    try:
        if not state["source_initialized"]:
            commit, data = source_payload(ref)
            with engine.begin() as connection:
                if connection.execute(text("SELECT to_regclass('public.anggota')")).scalar() is not None:
                    raise ValueError("Source exists but bootstrap state incomplete; refusing overwrite")
                connection.exec_driver_sql((ROOT / "sql/baseline/01_schema.sql").read_text(encoding="utf-8-sig"))
                connection.exec_driver_sql(data)
                if connection.execute(text("SELECT count(*) FROM anggota")).scalar_one() != 734:
                    raise ValueError("Source import count mismatch")
            state.update(source_initialized=True, dataset_commit=commit)
            save(state_file, state)
    finally:
        engine.dispose()
    os.environ["DATAGEN_DATABASE_URL"] = db_url(directory, state, "postgres", "postgres", "postgresql").render_as_string(hide_password=False)
    # Call C's unchanged generator/validator; relocate ONLY its report destination
    # to app/ to respect the B-only workspace rule. No replacement datagen logic.
    def record(name, payload):
        generator.guard_target(name)
        save(APP / "evidence/access-control/local-dataset.json", payload)
    generator.record = record
    before = checksum(generator.source_rows())
    with psycopg.connect(**generator.parameters("postgres"), autocommit=True) as db:
        exists = db.execute("SELECT 1 FROM pg_database WHERE datname=%s", ("baseline_100k",)).fetchone()
    if not exists:
        payload = generator.build("baseline_100k", 100000, seed=42)
        state["baseline_checksum"] = payload["baseline_checksum_sha256"]
        save(state_file, state)
    else:
        result = generator.validate_database("baseline_100k", 100000)
        if not result["passed"] or result["checksum_sha256"] != state.get("baseline_checksum"):
            raise ValueError("Existing baseline differs; refusing regeneration or silent adoption")
    after = checksum(generator.source_rows())
    if before != after:
        raise ValueError("Source changed during datagen")
    with psycopg.connect(db_url(directory, state, "postgres", driver="postgresql").render_as_string(hide_password=False)) as db:
        db.execute("SET LOCAL log_min_error_statement='panic'")
        db.execute("REVOKE ALL ON DATABASE baseline_100k FROM PUBLIC")
        db.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
        for role in ROLES:
            row = db.execute("SELECT rolsuper,rolcreatedb,rolcreaterole,rolbypassrls FROM pg_roles WHERE rolname=%s", (role,)).fetchone()
            if row is not None and any(row):
                raise ValueError("Existing role exceeds the lab privilege policy")
            if row is None:
                verifier = db.pgconn.encrypt_password(state["passwords"][role].encode(), role.encode(), b"scram-sha-256").decode()
                db.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}").format(sql.Identifier(role), sql.Literal(verifier)))
            db.execute(sql.SQL("GRANT CONNECT ON DATABASE baseline_100k TO {}").format(sql.Identifier(role)))
            db.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
        db.execute("CREATE OR REPLACE VIEW analyst_view WITH (security_barrier=true) AS SELECT jenis_kelamin,pekerjaan_terakhir,nama_kppn,nama_bank,CASE WHEN tanggal_lahir IS NULL THEN NULL ELSE ((extract(year from age(DATE '2026-10-01',tanggal_lahir))::int / 10)*10)::text || '-' || ((extract(year from age(DATE '2026-10-01',tanggal_lahir))::int / 10)*10+9)::text END AS age_band FROM anggota")
        from service_app.analytics import DIMENSIONS
        marginals = [f"SELECT '{field}'::text AS dimension, {field}::text AS value, count(*) AS anggota_count FROM public.analyst_view GROUP BY {field} HAVING count(*) >= 5" for field in DIMENSIONS]
        db.execute("CREATE OR REPLACE VIEW public.analyst_summary WITH (security_barrier=true) AS " + " UNION ALL ".join(marginals))
        db.execute("REVOKE ALL ON public.analyst_view FROM analyst_user")
        db.execute("GRANT SELECT ON public.analyst_summary TO analyst_user")
        db.execute("GRANT SELECT,INSERT,UPDATE ON anggota TO bench_user")
        db.execute("GRANT USAGE,SELECT ON SEQUENCE anggota_id_seq TO bench_user")
        db.execute("GRANT SELECT ON anggota TO scanner_user")
    os.environ["APP_SETUP_DATABASE_URL"] = db_url(directory, state, "postgres").render_as_string(hide_password=False)
    command([sys.executable, str(APP / "scripts/schema.py"), "--database", "baseline_100k"], env=os.environ.copy())
    # Local plain baseline RLS provisioning only; protected RLS remains owned by A.
    with psycopg.connect(db_url(directory, state, "postgres", driver="postgresql").render_as_string(hide_password=False)) as db:
        db.execute("ALTER TABLE anggota ENABLE ROW LEVEL SECURITY")
        db.execute("ALTER TABLE anggota FORCE ROW LEVEL SECURITY")
        if not db.execute("SELECT 1 FROM pg_policies WHERE tablename='anggota' AND policyname='service_b_local_scope'").fetchone():
            db.execute("CREATE POLICY service_b_local_scope ON anggota TO app_user USING (current_setting('app.role',true) IN ('operator','privileged_officer','finance_officer') OR (current_setting('app.role',true)='anggota' AND pengguna=current_setting('app.principal',true))) WITH CHECK (current_setting('app.role',true) IN ('operator','privileged_officer') OR (current_setting('app.role',true)='anggota' AND pengguna=current_setting('app.principal',true)))")
        if not db.execute("SELECT 1 FROM pg_policies WHERE tablename='anggota' AND policyname='service_b_local_benchmark'").fetchone():
            db.execute("CREATE POLICY service_b_local_benchmark ON anggota TO bench_user,scanner_user USING (true) WITH CHECK (current_user='bench_user')")
        principal = db.execute("SELECT pengguna FROM anggota WHERE id=1").fetchone()[0]
        populated = db.execute("SELECT count(*) FROM users").fetchone()[0]
    runtime_env = environment(directory, state)
    if not populated:
        command([sys.executable, str(APP / "scripts/provision.py")], env={**runtime_env, "DPR_PRIVATE_DIR": str(directory), "DEMO_MEMBER_PRINCIPAL": principal})
    elif not (directory / "service-b/service-b-plain-accounts.json").is_file():
        raise ValueError("Provisioned accounts lack original custody file")
    state["source_checksum"] = before
    save(state_file, state)
    return {"status": "PASSED", "database": "baseline_100k", "rows": 100000, "seed": 42,
            "source_rows": 734, "source_unchanged_after_bootstrap": before == after,
            "dataset_commit": state["dataset_commit"], "tls": "verify-full", "local_only": True}


def environment(directory, state):
    # Drop inherited credentials before supplying exactly the runtime identities.
    base = {k: v for k, v in os.environ.items() if not any(word in k.upper() for word in
            ("DATABASE_URL", "PASSWORD", "TOKEN", "SECRET", "PRIVATE_DIR", "ALLOW_DISPOSABLE"))}
    tls = directory / "runtime/tls"
    base.update(MODE="plain", DATABASE_URL=db_url(directory, state, "app_user").render_as_string(hide_password=False),
                ANALYST_DATABASE_URL=db_url(directory, state, "analyst_user").render_as_string(hide_password=False),
                AUDITOR_DATABASE_URL=db_url(directory, state, "auditor_user").render_as_string(hide_password=False),
                APP_ORIGIN="https://localhost:3443", SESSION_TTL_SECONDS="900", API_PORT="8100", WEB_PORT="3443",
                TLS_CERT_FILE=str(tls / "server.crt"), TLS_KEY_FILE=str(tls / "server.key"),
                NODE_EXTRA_CA_CERTS=str(tls / "ca.crt"), API_INTERNAL_URL="https://127.0.0.1:8100",
                NODE_ENV="production", NEXT_TELEMETRY_DISABLED="1")
    return base


def verify(directory):
    import ssl
    import psycopg
    from psycopg.rows import dict_row
    from datagen import database as generator
    from datagen.model import checksum
    from fastapi.testclient import TestClient
    from service_app.config import Settings
    from service_app.main import create_app
    from service_app.policy import detail_policy
    from integration_probe import check_database_roles, exercise_live_https, synthetic_row
    inspect_owned()
    state = load_state(directory)
    env = environment(directory, state)
    checks = {}
    report = {"schema_version": 1, "status": "FAILED", "mode": "plain", "database": "baseline_100k", "seed": 42,
              "scope": "Zhafif local pg-dpr; real team schema + Module C 100000-row seed42 dataset; six-role API and live HTTPS browser; not a performance benchmark or live protected proof",
              "dataset_commit": state["dataset_commit"], "checks": checks}
    report["code_commit"] = command(["git", "rev-parse", "HEAD"]).strip()
    report["app_worktree_dirty"] = bool(command(["git", "status", "--porcelain", "--", "app"]).strip())
    report["script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    os.environ["DATAGEN_DATABASE_URL"] = db_url(directory, state, "postgres", "postgres", "postgresql").render_as_string(hide_password=False)
    # A file lock prevents concurrent verify runs from restoring each other's changes.
    lock = directory / "verify.lock"
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    app = None
    mutation = None
    try:
        source_before = checksum(generator.source_rows())
        validation = generator.validate_database("baseline_100k", 100000)
        checks["datagen_validation"] = validation["passed"]
        checks["baseline_checksum_before"] = validation["checksum_sha256"] == state["baseline_checksum"]
        report["rows"] = validation["row_count"]
        if not checks["datagen_validation"] or not checks["baseline_checksum_before"]:
            raise ValueError("Baseline changed; refusing verification writes")
        with psycopg.connect(**generator.parameters("baseline_100k"), row_factory=dict_row) as db:
            db.execute("SET TRANSACTION READ ONLY")
            rows = db.execute("SELECT * FROM anggota ORDER BY id LIMIT 2").fetchall()
            seq_before = db.execute("SELECT last_value,is_called FROM anggota_id_seq").fetchone()
            report["postgres_server_version_num"] = db.info.server_version
        accounts = {a["role"]: {"username": a["username"], "password": a["password"]} for a in
                    json.loads((directory / "service-b/service-b-plain-accounts.json").read_text(encoding="utf-8"))}
        urls = {r: db_url(directory, state, r) for r in ("app_user", "analyst_user", "auditor_user")}
        check_database_roles(urls, checks, rows[0]["pengguna"])
        with psycopg.connect(db_url(directory, state, "postgres", driver="postgresql").render_as_string(hide_password=False)) as db:
            checks["pg18"] = 180000 <= db.info.server_version < 190000
        try:
            with psycopg.connect(db_url(directory, state, "app_user", driver="postgresql").render_as_string(hide_password=False), sslmode="disable", connect_timeout=3):
                checks["non_tls_rejected"] = False
        except psycopg.OperationalError:
            checks["non_tls_rejected"] = True
        import tempfile
        from infra.tls.make_ca import make_ca
        with tempfile.TemporaryDirectory(prefix="dpr-local-wrongca-") as temp:
            make_ca(Path(temp) / "tls")
            try:
                with psycopg.connect(db_url(directory, state, "app_user", driver="postgresql").render_as_string(hide_password=False), sslrootcert=str(Path(temp) / "tls/ca.crt"), connect_timeout=3):
                    checks["wrong_ca_rejected"] = False
            except psycopg.OperationalError:
                checks["wrong_ca_rejected"] = True
        settings = Settings(mode="plain", database_url=env["DATABASE_URL"], analyst_database_url=env["ANALYST_DATABASE_URL"],
                            auditor_database_url=env["AUDITOR_DATABASE_URL"], app_origin=env["APP_ORIGIN"])
        app = create_app(settings)
        with TestClient(app, base_url=settings.app_origin) as client:
            checks["unauthenticated_denied"] = client.get("/anggota").status_code == 401
            for role, account in accounts.items():
                client.cookies.clear()
                client.get("/auth/csrf")
                headers = {"X-CSRF-Token": client.cookies.get("dpr_csrf", ""), "Origin": settings.app_origin}
                login = client.post("/auth/login", json=account, headers=headers)
                checks["login:" + role] = login.status_code == 200
                headers["X-CSRF-Token"] = client.cookies.get("dpr_csrf", "")
                detail = client.get("/anggota/1")
                if role in {"analyst", "auditor"}:
                    checks["detail_denied:" + role] = detail.status_code == 403
                    checks["list_denied:" + role] = client.get("/anggota").status_code == 403
                    response = client.get("/analytics/summary" if role == "analyst" else "/audit")
                    checks["own_endpoint:" + role] = response.status_code == 200
                    if role == "analyst":
                        body = response.json()
                        checks["A5_total_unavailable"] = body.get("total") is None
                        checks["A5_threshold"] = all(g["count"] >= 5 for g in body.get("groups", []))
                        checks["A5_released_group"] = bool(body.get("groups"))
                    continue
                policy = detail_policy(role)
                checks["exact_dto:" + role] = detail.status_code == 200 and set(detail.json()) == {"anggota_id", *policy.fields}
                for field in policy.fields - policy.masked:
                    original = rows[0][field]
                    expected = original.isoformat() if isinstance(original, date) else str(original) if original is not None else None
                    checks[f"correctness:{role}:{field}"] = detail.json().get(field) == expected
                listed = client.get("/anggota?page=1").json()
                expected_count = 1 if role == "anggota" else 100000
                checks["list_total:" + role] = listed.get("total") == expected_count and listed.get("page_size") == 50
                checks["list_allowlist:" + role] = all(set(row) == {"anggota_id", "nama"} for row in listed.get("items", []))
                checks["email_lookup:" + role] = client.get("/anggota/search", params={"email": rows[0]["email"]}).json().get("total") == 1
                checks["ktp_lookup:" + role] = client.get("/anggota/search", params={"no_ktp": rows[0]["no_ktp"]}).json().get("total") == 1
                checks["injection:" + role] = client.get("/anggota/search", params={"email": "' OR 1=1 --"}).status_code == 422
                if role == "anggota":
                    checks["idor_detail"] = client.get("/anggota/2").status_code == 404
                    checks["idor_patch"] = client.patch("/anggota/2/kontak", json={"email": "denied@example.test"}, headers=headers).status_code == 404
                if role == "privileged_officer":
                    last = client.get("/anggota?page=2000").json()
                    checks["last_page_100k"] = len(last.get("items", [])) == 50 and last["items"][-1]["anggota_id"] == "100000"
                    mutation = synthetic_row(secrets.randbelow(9000) + 1000)
                    created = client.post("/anggota", json=mutation, headers=headers)
                    checks["insert"] = created.status_code == 201
                    if created.status_code == 201:
                        mutation["id"] = int(created.json()["anggota_id"])
                    patch = client.patch("/anggota/1/kontak", json={"email": "local-verify@example.test"}, headers=headers)
                    checks["patch"] = patch.status_code == 200
                    restored = client.patch("/anggota/1/kontak", json={"email": rows[0]["email"]}, headers=headers)
                    checks["patch_restore"] = restored.status_code == 200
                checks["logout:" + role] = client.post("/auth/logout", headers=headers).status_code == 200
        # Remove only this run's insert BEFORE the browser verifies total/aggregates.
        cleanup_insert(state, directory, mutation, seq_before)
        mutation = None
        exercise_live_https(settings, accounts, directory / "runtime", checks)
    except Exception as exc:
        report["failure_class"] = type(exc).__name__
    finally:
        if app:
            app.state.engine.dispose()
            app.state.auth_engine.dispose()
        if "rows" in locals():
            # Always restore touched contacts with bound values, even if the UI failed.
            try:
                with psycopg.connect(**generator.parameters("baseline_100k")) as db:
                    db.execute("UPDATE anggota SET email=%s,handphone=%s WHERE id=%s", (rows[0]["email"], rows[0]["handphone"], rows[0]["id"]))
                cleanup_insert(state, directory, mutation, seq_before)
                validation = generator.validate_database("baseline_100k", 100000)
                checks["baseline_checksum_restored"] = validation["passed"] and validation["checksum_sha256"] == state["baseline_checksum"]
                checks["source_checksum_unchanged"] = checksum(generator.source_rows()) == state["source_checksum"]
            except Exception:
                checks["baseline_checksum_restored"] = False
        os.close(descriptor)
        lock.unlink()
        report["checked_at_utc"] = datetime.now(timezone.utc).isoformat()
        report["status"] = "PASSED" if checks and all(checks.values()) and "failure_class" not in report else "FAILED"
        save(APP / "evidence/access-control/baseline-100k.json", report)
    return {"status": report["status"], "checks": len(checks), "failed_checks": [k for k, v in checks.items() if not v],
            **({"failure_class": report["failure_class"]} if "failure_class" in report else {})}


def cleanup_insert(state, directory, mutation, sequence):
    if not mutation or "id" not in mutation:
        return
    if mutation["id"] != 100001:
        raise ValueError("Unexpected concurrent insert; refusing cleanup")
    import psycopg
    with psycopg.connect(db_url(directory, state, "postgres", driver="postgresql").render_as_string(hide_password=False)) as db:
        deleted = db.execute("DELETE FROM anggota WHERE id=%s AND pengguna=%s AND no_ktp=%s RETURNING id",
                             (mutation["id"], mutation["pengguna"], mutation["no_ktp"])).fetchone()
        if deleted is None:
            raise ValueError("Cannot identify the exact verification insert")
        current = db.execute("SELECT last_value FROM anggota_id_seq").fetchone()[0]
        if current != mutation["id"]:
            raise ValueError("Concurrent sequence modification; refusing reset")
        db.execute("SELECT setval('anggota_id_seq',%s,%s)", (sequence["last_value"], sequence["is_called"]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["setup", "verify", "backend", "web"])
    parser.add_argument("--dataset-ref", default="origin/main")
    args = parser.parse_args()
    directory = private_directory()
    if args.action == "setup":
        value = setup(directory, args.dataset_ref)
        save(APP / "evidence/access-control/local-lab-setup.json", value)
    elif args.action == "verify":
        value = verify(directory)
    else:
        inspect_owned()
        env = environment(directory, load_state(directory))
        # Foreground child is stopped when this launcher exits; secrets aren't shell args.
        arguments = [sys.executable, str(APP / "scripts/serve.py")] if args.action == "backend" else ["node", "server.mjs"]
        child = subprocess.Popen(arguments, cwd=ROOT if args.action == "backend" else APP / "web", env=env)
        try:
            return child.wait()
        finally:
            from integration_probe import stop_owned_process
            stop_owned_process(child)
    print(json.dumps(value))
    return 0 if value["status"] == "PASSED" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"status": "FAILED", "failure_class": type(exc).__name__, "details": "withheld; inspect configuration without printing secrets"}))
        raise SystemExit(1) from None
