"""734-record setup/import/assessment/migration/application/restore acceptance."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
import yaml

from dprcrypto import OpenBaoClient
from dprcrypto.vectors import verify_document
from infra.acceptance import browser
from infra.openbao.api import BaoAPI, BaoError
from infra.openbao.init import initialize, unseal, configure, issue_tokens, revoke_migration
from infra.postgres.development import read_source
from infra.protected.apply import load_profile, provision
from infra.protected.credentials import ROLES
from infra.security import secure_directory, write_private
from migration.runner import execute, source_summary
from policy.build_profile import build, text_hashes
from scripts.backup.drills import tamper_test, retention_test
from scripts.backup.postgres import drop_created_database
from scripts.backup.runner import backup, restore
from scripts.backup.settings import artifact_store
from .bootstrap import ROOT, python_bin
from .stack import Stack, clean_environment, environment, free_port


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def contract_checks():
    # JSON vectors contain non-ASCII test plaintext. Never use the Windows ANSI
    # default codec; ciphertext/AAD and the shared vector file remain unchanged.
    document = json.loads((ROOT / "docs/contracts/test_vectors.json").read_bytes().decode("utf-8"))
    return {"vector:" + key: value for key, value in verify_document(document).items()}


def call(command, *, env, timeout=300):
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError("Reproduction step failed; output withheld")


def import_data(stack, rows, passwords):
    with stack.connection(autocommit=True) as admin:
        admin.execute("CREATE DATABASE protected_734 TEMPLATE template0")
        for name in ("postgres", "protected_734"):
            admin.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(name)))
    # No DROP/overwrite statement is ever run, including the baseline script's DROP.
    ddl = (ROOT / "sql/baseline/01_schema.sql").read_text(encoding="utf-8-sig")
    if ddl.count("DROP TABLE IF EXISTS anggota;") != 1:
        raise ValueError("Unexpected source DDL")
    ddl = ddl.replace("DROP TABLE IF EXISTS anggota;", "")
    with stack.connection() as admin:
        if admin.execute("SELECT to_regclass('public.anggota')").fetchone()[0] is not None:
            raise ValueError("Initial import refuses overwrite")
        admin.execute(ddl)
        columns = list(rows[0])
        query = sql.SQL("INSERT INTO public.anggota ({}) VALUES ({})").format(
            sql.SQL(",").join(map(sql.Identifier, columns)), sql.SQL(",").join(sql.Placeholder() for _ in columns))
        with admin.cursor() as cursor:
            cursor.executemany(query, [[row[key] for key in columns] for row in rows])
        if admin.execute("SELECT count(*) FROM public.anggota").fetchone()[0] != 734:
            raise ValueError("Expected 734 source records")
        # Create the source reader before assessment; no runtime role gets source access.
        admin.execute(sql.SQL("CREATE ROLE scanner_user LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD {}").format(
            sql.Literal(passwords["scanner_user"])))
        admin.execute("GRANT CONNECT ON DATABASE postgres TO scanner_user")
        admin.execute("GRANT USAGE ON SCHEMA public TO scanner_user")
        admin.execute("GRANT SELECT ON public.anggota TO scanner_user")


def assess(stack, passwords, output):
    scanner = python_bin(ROOT / ".venv-assessment")
    if not scanner.is_file():
        raise RuntimeError("Run setup for the assessment environment")
    params = stack.parameters("postgres", "scanner_user", passwords["scanner_user"])
    env = {**clean_environment(), "SCANNER_DATABASE_URL": make_conninfo(**params)}
    destination = output / "scanner"
    call([str(scanner), "-m", "scanner", "db", "--sample", "1000", "--label", "before", "--out", str(destination)], env=env)
    call([str(scanner), "-m", "scanner", "evaluate", "--pred", str(destination / "inventory.csv"),
          "--truth", "scanner/ground_truth_eval.csv", "--out", str(destination / "evaluation.json")], env=clean_environment())
    profile = build(destination / "inventory.csv", ROOT / "policy/overrides.yaml", ROOT / "docs/contracts/CONTRACT.md")
    path = output / "protection_profile.yaml"
    path.write_text(yaml.safe_dump(profile, sort_keys=False, allow_unicode=True), encoding="utf-8")
    # Apply the profile from THIS scan, including its verified provenance.
    load_profile(path)
    return profile, path


def bao(stack):
    address = f"https://127.0.0.1:{stack.bao_port}"
    api = BaoAPI(address, str(stack.root / "tls/ca.crt"))
    for _ in range(100):
        try:
            state = api.request("/sys/seal-status")
            break
        except BaoError:
            time.sleep(.2)
    else:
        raise RuntimeError("Fresh OpenBao startup timeout")
    if state["initialized"]:
        raise ValueError("Fresh reproduction refuses an existing key plane")
    initialize(api, stack.root)
    material = json.loads((stack.root / "openbao/init-material.json").read_text())
    # Only this invocation's NEW disposable key plane, never an existing service.
    for share in material["keys_base64"][:2]:
        unseal(api, share)
    configure(api, material["root_token"])
    issue_tokens(api, material["root_token"], stack.root, 3600)
    tokens = {policy: json.loads(next((stack.root / "openbao/tokens").glob(policy + "-*.json")).read_text())["auth"]["client_token"]
              for policy in ("svc-app", "svc-migration")}
    return api, tokens


def migrate(stack, passwords, profile, profile_path, tokens, api):
    env = {"OPENBAO_ADDR": f"https://127.0.0.1:{stack.bao_port}", "OPENBAO_CACERT": str(stack.root / "tls/ca.crt"),
           "OPENBAO_MIGRATION_TOKEN": tokens["svc-migration"], "OPENBAO_VALIDATION_TOKEN": tokens["svc-app"]}
    with environment(env), OpenBaoClient(token_env="OPENBAO_MIGRATION_TOKEN") as writer, \
            OpenBaoClient(token_env="OPENBAO_VALIDATION_TOKEN") as verifier, \
            stack.connection("postgres", "scanner_user", passwords["scanner_user"], autocommit=True, row_factory=dict_row) as source, \
            stack.connection("protected_734", "migration_user", passwords["migration_user"], autocommit=True, row_factory=dict_row) as target:
        hashes = text_hashes(profile_path)
        result = execute(source, target, source_name="postgres", target_name="protected_734", profile=profile,
                         profile_hash=hashes[0], compatible_profile_hashes=hashes[1:], migration_client=writer,
                         validation_client=verifier, batch_size=1000, expected_rows=734)
        # Second run must resume as complete without creating duplicate records.
        repeated = execute(source, target, source_name="postgres", target_name="protected_734", profile=profile,
                           profile_hash=hashes[0], compatible_profile_hashes=hashes[1:], migration_client=writer,
                           validation_client=verifier, batch_size=1000, expected_rows=734)
    if not result["passed"] or not repeated["passed"] or repeated["migrated_rows"] != 734:
        raise ValueError("Full migration/resume validation failed")
    revoke_migration(api, tokens["svc-migration"])
    try:
        api.request("/auth/token/lookup-self", token=tokens["svc-migration"])
    except BaoError as error:
        if error.status != 403:
            raise
    else:
        raise ValueError("Migration token still accepted")
    with stack.connection("protected_734") as admin:
        admin.execute("ALTER ROLE migration_user NOLOGIN")
    return {**result, "repeat_run_idempotent": True, "migration_token_revoked": True, "migration_role_nologin": True}


def service_settings(stack, passwords, tokens, *, database="protected_734", restored=False):
    sys.path.insert(0, str(ROOT / "app/backend"))
    from service_app.config import Settings
    def url(role):
        return URL.create("postgresql+psycopg", username=role, password=passwords[role], host="127.0.0.1",
                          port=stack.pg_port, database=database,
                          query={"sslmode": "verify-full", "sslrootcert": str(stack.root / "postgres/tls/ca.crt")}).render_as_string(hide_password=False)
    return Settings(mode="protected", database_url=url("app_user"), auth_database_url=url("app_user"),
                    analyst_database_url=url("analyst_user"), auditor_database_url=url("auditor_user"),
                    restored_database=database if restored else None, openbao_addr=f"https://127.0.0.1:{stack.bao_port}",
                    openbao_cacert=str(stack.root / "tls/ca.crt"), openbao_token=tokens["svc-app"]).validate()


def provision_service(stack, passwords, tokens, rows):
    settings = service_settings(stack, passwords, tokens)
    spec = importlib.util.spec_from_file_location("dpr_reproduction_schema", ROOT / "app/scripts/schema.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    url = URL.create("postgresql+psycopg", username="dpr_bootstrap", password=stack.password, host="127.0.0.1",
                     port=stack.pg_port, database="protected_734",
                     query={"sslmode": "verify-full", "sslrootcert": str(stack.root / "postgres/tls/ca.crt")}).render_as_string(hide_password=False)
    engine = create_engine(url, hide_parameters=True)
    try:
        module.setup_protected(engine)
    finally:
        engine.dispose()
    with stack.connection("protected_734") as admin:
        admin.execute((ROOT / "sql/protected/04_identity_unique.sql").read_text(encoding="utf-8"))
    env = {**clean_environment(), "MODE": "protected", "DATABASE_URL": settings.database_url,
           "AUTH_DATABASE_URL": settings.auth_database_url, "ANALYST_DATABASE_URL": settings.analyst_database_url,
           "AUDITOR_DATABASE_URL": settings.auditor_database_url, "APP_SETUP_DATABASE_URL": url,
           "OPENBAO_ADDR": settings.openbao_addr, "OPENBAO_CACERT": settings.openbao_cacert,
           "OPENBAO_TOKEN": tokens["svc-app"], "DPR_CRYPTO_FACTORY": "dprcrypto:public-v1",
           "DPR_PRIVATE_DIR": str(stack.root), "DEMO_ASSIGNED_IDS": "1,2", "DEMO_MEMBER_PRINCIPAL": rows[0]["pengguna"]}
    call([sys.executable, "app/scripts/provision.py"], env=env)
    accounts_path = stack.root / "service-b/service-b-protected-accounts.json"
    accounts = {account["role"]: {"username": account["username"], "password": account["password"]}
                for account in json.loads(accounts_path.read_text())}
    return settings, accounts


def database_checks(stack, passwords):
    checks = {}
    for role in ("app_user", "analyst_user", "auditor_user"):
        params = stack.parameters("protected_734", role, passwords[role])
        with psycopg.connect(**params, autocommit=True) as connection:
            checks[role + ":tls"] = connection.execute("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()").fetchone()[0]
            if role == "app_user":
                checks["rls_default_denies"] = connection.execute("SELECT count(*) FROM anggota_protected").fetchone()[0] == 0
            else:
                for name in ("anggota_protected", "analyst_view"):
                    try:
                        connection.execute(sql.SQL("SELECT * FROM public.{}").format(sql.Identifier(name)))
                    except psycopg.errors.InsufficientPrivilege:
                        checks[role + ":denied:" + name] = True
                    else:
                        checks[role + ":denied:" + name] = False
            if role == "analyst_user":
                checks["a5_no_small_groups"] = connection.execute("SELECT count(*) FROM analyst_summary WHERE anggota_count<5").fetchone()[0] == 0
                checks["a5_large_groups_present"] = connection.execute("SELECT count(*) FROM analyst_summary").fetchone()[0] > 0
        for label, changed in (("no_tls", {"sslmode": "disable"}),
                               ("wrong_host", {"host": "wrong-host.invalid", "hostaddr": "127.0.0.1"})):
            try:
                with psycopg.connect(**{**params, **changed}):
                    pass
            except psycopg.OperationalError:
                checks[role + ":reject:" + label] = True
            else:
                checks[role + ":reject:" + label] = False
    return checks


@contextmanager
def services(settings, stack, tokens):
    """Foreground-owned processes, runtime env stripped of operator credentials."""
    api_port, web_port = free_port(), free_port()
    while api_port == web_port:
        web_port = free_port()
    api_env, web_env = browser.environments(settings, stack.root, api_port, web_port)
    api_env = {key: value for key, value in api_env.items() if value is not None}
    api = web = None
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    try:
        api = subprocess.Popen([sys.executable, str(ROOT / "app/scripts/serve.py")], cwd=ROOT, env=api_env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **flags)
        if not browser.wait_https(f"https://127.0.0.1:{api_port}/health/ready", stack.root / "tls/ca.crt", api):
            raise RuntimeError("Demo API not ready")
        web = subprocess.Popen([shutil.which("node"), "server.mjs"], cwd=ROOT / "app/web", env=web_env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **flags)
        if not browser.wait_https(web_env["APP_ORIGIN"] + "/login", stack.root / "tls/ca.crt", web):
            raise RuntimeError("Demo frontend not ready")
        yield web_env["APP_ORIGIN"]
    finally:
        browser.stop_owned_process(web)
        browser.stop_owned_process(api)


def verify_services(stack, passwords, tokens, profile_path, accounts, output):
    env = {"OPENBAO_ADDR": f"https://127.0.0.1:{stack.bao_port}", "OPENBAO_CACERT": str(stack.root / "tls/ca.crt"),
           "OPENBAO_VALIDATION_TOKEN": tokens["svc-app"]}
    if stack.pg_bin:
        env["DPR_BACKUP_NATIVE_PG_BIN"] = str(stack.pg_bin)
    created = []
    with environment(env):
        try:
            keys = (secrets.token_bytes(32), secrets.token_bytes(32))
            # Backup recovery keys are independent, private and never CLI arguments.
            write_private(stack.root / "backup-keys.bin", b"".join(keys))
            store = artifact_store(str(stack.root / "archives"))
            artifact = backup("protected_734", stack.parameters("protected_734", "backup_user", passwords["backup_user"]),
                              keys, store, container=stack.container)
            save(output / "backup.json", {key: artifact[key] for key in ("backup_seconds", "size_bytes", "artifact_id")})
            without = restore(artifact["manifest"], stack.parameters(), keys, container=stack.container)
            created.append(without["created_database"])
            recovered = restore(artifact["manifest"], stack.parameters(), keys, container=stack.container,
                                with_openbao=True, profile_path=profile_path)
            created.append(recovered["created_database"])
            save(output / "restore-without-openbao.json", without)
            save(output / "restore-with-openbao.json", recovered)
            tamper = tamper_test(artifact["manifest"], stack.parameters(), keys, container=stack.container)
            save(output / "tamper.json", tamper)
            retention = retention_test(artifact["manifest"], stack.parameters(),
                                       stack.parameters("protected_734", "backup_user", passwords["backup_user"]),
                                       keys, store, container=stack.container, profile_path=profile_path)
            save(output / "retention.json", retention)
            settings = service_settings(stack, passwords, tokens, database=recovered["database"], restored=True)
            observed = browser.exercise(settings, accounts, stack.root)
            save(output / "browser.json", observed)
            return {"restore_without_decrypt": not without["decryption_smoke"]["performed"],
                    "restore_with_decrypt": recovered["decryption_smoke"]["records"] > 0,
                    "tampered_backup_rejected": tamper["passed"], "retention_passed": retention["passed"],
                    "six_account_restored_browser": observed["status"] == "PASSED"}
        finally:
            for identity in reversed(created):
                drop_created_database(stack.parameters(), identity)


def run(args):
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex[:8]
    output = ROOT / "evidence/reproduction" / run_id
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema_version": 1, "passed": False, "run_id": run_id,
              "checked_at_utc": datetime.now(timezone.utc).isoformat(), "stages": {},
              "source_rows": 734, "official_benchmark": False,
              "scope": "Fresh isolated 734-record reproduction, no existing team database/service accessed"}
    stage = "preflight"
    try:
        if not args.data.is_file() or not (ROOT / "app/web/.next/BUILD_ID").is_file():
            raise ValueError("Dataset and setup frontend build are required")
        rows = read_source(args.data)
        assessment = python_bin(ROOT / ".venv-assessment")
        if not assessment.is_file():
            raise ValueError("Setup assessment environment first")
        private_base = Path(tempfile.gettempdir()) / "dpr-reproduction"
        secure_directory(private_base)
        private = private_base / run_id
        report["transport"] = "native_pg18_openbao_tls" if args.native_pg_bin else "docker_pg18_openbao_tls"
        for name in ("setup", "import", "assessment", "hardening", "service_application", "security_verification"):
            report["stages"][name] = {"status": "NOT_RUN"}
        print("Fresh demo only: bootstrap recovery material stays outside Git; auto-unseal is confined to the NEW disposable key plane.", flush=True)
        stage = "setup"
        with Stack(private, pg_bin=args.native_pg_bin, bao_bin=args.native_bao_bin) as stack:
            report["stages"][stage] = {"status": "PASS"}
            passwords = {role: secrets.token_urlsafe(36) for role in ROLES}
            stage = "import"
            import_data(stack, rows, passwords)
            report["stages"][stage] = {"status": "PASS", "rows": 734}
            print("Import PASS (734). Running assessment...", flush=True)
            stage = "assessment"
            profile, profile_path = assess(stack, passwords, output)
            report["stages"][stage] = {"status": "PASS", "columns": len(profile["columns"]), "profile": profile_path.relative_to(ROOT).as_posix()}
            stage = "hardening"
            api, tokens = bao(stack)
            with environment(stack.pg_environment()):
                provision(stack.container, "protected_734", "dpr_bootstrap", passwords, profile,
                          psql_bin=Path(stack.executable("psql")) if stack.pg_bin else None)
            migrated = migrate(stack, passwords, profile, profile_path, tokens, api)
            save(output / "migration.json", migrated)
            report["stages"][stage] = {"status": "PASS", "rows_compared": migrated["rows_compared"], "resume_checked": True}
            print("Assessment and hardening PASS. Provisioning service accounts...", flush=True)
            stage = "service_application"
            settings, accounts = provision_service(stack, passwords, tokens, rows)
            report["stages"][stage] = {"status": "PASS", "accounts": len(accounts)}
            stage = "security_verification"
            checks = database_checks(stack, passwords)
            checks.update(contract_checks())
            checks.update(verify_services(stack, passwords, tokens, profile_path, accounts, output))
            with stack.connection("postgres", "scanner_user", passwords["scanner_user"], row_factory=dict_row) as source:
                checks["source_734_unchanged"] = source_summary(source, profile)["sha256"] == migrated["source_sha256"]
            save(output / "security.json", {"passed": all(checks.values()), "checks": checks})
            report["stages"][stage] = {"status": "PASS" if all(checks.values()) else "FAIL", "checks": len(checks)}
            if not all(checks.values()):
                raise ValueError("Security checks failed")
            report["passed"] = True
            if args.command == "demo":
                with environment({"OPENBAO_VALIDATION_TOKEN": tokens["svc-app"]}), services(settings, stack, tokens) as origin:
                    print("Demo: " + origin + "/login", flush=True)
                    print("Private accounts: " + str(stack.root / "service-b/service-b-protected-accounts.json"), flush=True)
                    print("Local browser CA: " + str(stack.root / "tls/ca.crt"), flush=True)
                    print("Ctrl+C stops ONLY this demo. Runtime token expires after 1 hour.", flush=True)
                    try:
                        while True:
                            time.sleep(1)
                    except KeyboardInterrupt:
                        pass
        report["owned_services_stopped"] = True
    except (Exception, KeyboardInterrupt) as error:
        report["passed"] = False
        report["failed_stage"] = stage
        report["error_type"] = type(error).__name__
        import traceback
        report["error_locations"] = [{"file": Path(item.filename).name, "function": item.name, "line": item.lineno}
                                     for item in traceback.extract_tb(error.__traceback__)[-5:]]
        report["details"] = "withheld; no DSN, SQL values or credentials emitted"
        if stage in report["stages"]:
            report["stages"][stage]["status"] = "FAIL"
    finally:
        save(output / "summary.json", report)
        print(json.dumps({"passed": report["passed"], "report": str((output / "summary.json").relative_to(ROOT)),
                          "failed_stage": report.get("failed_stage")}))
    return 0 if report["passed"] else 1
