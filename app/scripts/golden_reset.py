"""Guarded VM-only template snapshot/reset. The explicit reset replaces protected_734.

Never use against a benchmark/laptop cluster. Metadata and audit exports are private.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "app/backend"), str(ROOT / "app/scripts")]

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from infra.protected.analyst import security_checks
from infra.protected.credentials import ROLES
from infra.security import external_directory, secure_directory, write_private
from infra.vm.operator import database_parameters
from pentest_prepare import TARGET, read_private, setup_url
from pentest_smoke import smoke
from service_app.config import Settings

GOLDEN = "protected_734_golden"
UNITS = ("dpr-web.service", "dpr-api.service")
LOCK_ID = 73420261028
FORMAT = "dpr-pentest-golden-v1"


def run_command(arguments):
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=90, check=True)
    return result.stdout.strip()


def service_guard():
    if os.name != "posix" or ROOT != Path("/home/ubuntu/juara1onno"):
        raise ValueError("Golden operations require the approved Ubuntu deployment")
    for name in UNITS:
        installed = Path("/etc/systemd/system") / name
        source = ROOT / "app/deploy" / name
        if installed.is_symlink() or not installed.is_file() or installed.read_bytes() != source.read_bytes():
            raise ValueError("Install the two reviewed application units before golden operations")
    if run_command(["docker", "inspect", "--format", '{{index .Config.Labels "dpr.scope"}}', "dpr-demo-postgres-1"]) != "vm-demo":
        raise ValueError("Refusing a cluster outside the dedicated VM project")


def control_app(action):
    if action not in {"start", "stop"}:
        raise ValueError("Invalid service action")
    run_command(["sudo", "-n", "systemctl", action, *UNITS])


def database_state(root):
    with psycopg.connect(**database_parameters(root, TARGET, readonly=True)) as db:
        count = db.execute("SELECT count(*) FROM public.anggota_protected").fetchone()[0]
        if count != 734 or not all(security_checks(db).values()):
            raise ValueError("Expected the validated 734-member service with A5")
        owner, rls = db.execute("SELECT pg_get_userbyid(relowner),relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid='public.anggota_protected'::regclass").fetchone()
        if owner != "schema_owner" or not rls:
            raise ValueError("Member ownership/RLS changed")
    return {"members": count, "A5": True, "forced_rls": True}


def safe_audit_row(row):
    result = {"event_id": int(row["event_id"]), "occurred_at": row["occurred_at"].isoformat()}
    for field in ("actor", "anggota_id", "request_id"):
        try:
            result[field] = str(UUID(str(row[field]))) if row[field] is not None else None
        except ValueError:
            result[field] = None
    allowed_actions = {"login", "logout", "list", "search", "detail", "decrypt", "update", "insert", "analytics", "audit", "audit.read", "auth.required", "csrf"}
    allowed_actions.update(table + "." + operation for table in ("app_users", "access_scope", "anggota_protected") for operation in ("insert", "update", "delete"))
    result["action"] = row["action"] if row["action"] in allowed_actions else "unrecognized_event"
    for field in ("actor_role", "database_user", "effective_role"):
        allowed = {"operator", "privileged_officer", "finance_officer", "analyst", "auditor", "anggota", "database", "anonymous", "postgres", "schema_owner", *ROLES}
        result[field] = row[field] if row[field] in allowed else "unknown"
    result["field_class"] = row["field_class"] if row["field_class"] in {"PII", "FIN", "REF", "AUTH", "SCOPE", "ROW"} else "unknown"
    result["decision"] = row["decision"] if row["decision"] in {"allowed", "denied", "error"} else "unknown"
    return result


def export_audit(root, directory):
    directory = secure_directory(external_directory(str(directory)))
    destination = directory / ("audit-" + uuid4().hex + ".jsonl")
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    count = 0
    with os.fdopen(fd, "w", encoding="utf-8") as output, \
            psycopg.connect(**database_parameters(root, TARGET, readonly=True), row_factory=dict_row) as db:
        with db.cursor(name="pentest_audit_export") as rows:
            rows.execute("SELECT event_id,occurred_at,actor,actor_role,database_user,effective_role,action,anggota_id,field_class,decision,request_id FROM public.audit_log ORDER BY event_id")
            for row in rows:
                output.write(json.dumps(safe_audit_row(row)) + "\n")
                count += 1
        output.flush()
        os.fsync(output.fileno())
    return {"path": str(destination), "events": count, "metadata_only": True}


def save_metadata(path, document, *, replace=False):
    if path.is_symlink():
        raise ValueError("Refusing a golden metadata symlink")
    if not replace:
        write_private(path, (json.dumps(document, indent=2) + "\n").encode())
        return
    temporary = path.with_name(".golden-" + uuid4().hex + ".tmp")
    try:
        write_private(temporary, (json.dumps(document, indent=2) + "\n").encode())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_golden(metadata, system_id, live_oid, golden):
    if (metadata.get("format") != FORMAT or metadata.get("target") != TARGET or metadata.get("golden") != GOLDEN
            or metadata.get("members") != 734 or metadata.get("system_identifier") != str(system_id)
            or metadata.get("live_oid") != live_oid or golden is None
            or metadata.get("golden_oid") != golden[0] or golden[1] is not False
            or metadata.get("marker") != golden[2]):
        raise ValueError("Golden/live database identity changed; no destructive action allowed")


def wait_and_smoke():
    result = {"passed": False}
    # Services may need a few seconds to bind; do not repeatedly attempt logins
    # after a real failed smoke check (which would consume the rate limit).
    import httpx
    import ssl
    context = ssl.create_default_context(cafile=os.environ["NODE_EXTRA_CA_CERTS"])
    for _ in range(30):
        try:
            with httpx.Client(verify=context, trust_env=False, timeout=2) as client:
                if client.get("https://127.0.0.1:3443/api/health/ready").status_code == 200:
                    return smoke()
        except httpx.HTTPError:
            pass
        time.sleep(1)
    return result


def operate(command, root, directory):
    if command not in {"create", "reset"}:
        raise ValueError("Invalid golden operation")
    service_guard()
    directory = secure_directory(external_directory(str(directory)))
    metadata_file = directory / "golden-template.json"
    params = database_parameters(root, "postgres")
    if params["host"] not in {"127.0.0.1", "localhost"} or params["port"] != 5433:
        raise ValueError("Only the approved local VM database endpoint is allowed")
    report = {"passed": False, "target": TARGET, "golden": GOLDEN, "command": command}
    with psycopg.connect(**params, autocommit=True) as admin:
        version, encrypted, system_id = admin.execute("SELECT current_setting('server_version_num')::int,(SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()),system_identifier::text FROM pg_control_system()").fetchone()
        if not 180000 <= version < 190000 or not encrypted:
            raise ValueError("PG18 and verified TLS required")
        if not admin.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_ID,)).fetchone()[0]:
            raise ValueError("Another golden operation is running")
        live = admin.execute("SELECT oid FROM pg_database WHERE datname=%s", (TARGET,)).fetchone()
        golden = admin.execute("SELECT oid,datallowconn,shobj_description(oid,'pg_database') FROM pg_database WHERE datname=%s", (GOLDEN,)).fetchone()
        if live is None:
            raise ValueError("Live target missing; preserve golden and contact recovery owner")
        if command == "create" and (golden is not None or metadata_file.exists()):
            validate_golden(read_private(metadata_file), system_id, live[0], golden)
            return {**report, "passed": True, "existing_preserved": True, "members": 734}
        if command == "reset":
            metadata = read_private(metadata_file)
            validate_golden(metadata, system_id, live[0], golden)
        else:
            database_state(root)
            if admin.execute("SELECT count(*) FROM pg_db_role_setting WHERE setdatabase=%s", (live[0],)).fetchone()[0] != 0:
                raise ValueError("Custom per-database settings need review before a template reset")
        # Creation must freeze a working app. Reset must also recover an app
        # whose pt scopes/accounts/data were deliberately damaged by pentesting.
        if command == "create" and not smoke().get("passed"):
            raise ValueError("Pre-operation app smoke failed; no stop/drop performed")
        report["audit_before_stop"] = export_audit(root, directory / "audit")
        control_app("stop")
        # Capture any audit events that arrived between the first export and stop.
        report["audit_final"] = export_audit(root, directory / "audit")
        if command == "reset":
            admin.execute(sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS false").format(sql.Identifier(TARGET)))
        admin.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid()", (TARGET,))
        if command == "create":
            marker = "dpr-pentest-golden-v1:" + uuid4().hex
            admin.execute(sql.SQL("CREATE DATABASE {} WITH TEMPLATE {} ALLOW_CONNECTIONS false").format(sql.Identifier(GOLDEN), sql.Identifier(TARGET)))
            admin.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(GOLDEN)))
            admin.execute(sql.SQL("COMMENT ON DATABASE {} IS {}").format(sql.Identifier(GOLDEN), sql.Literal(marker)))
            golden_oid = admin.execute("SELECT oid FROM pg_database WHERE datname=%s", (GOLDEN,)).fetchone()[0]
            metadata = {"format": FORMAT, "target": TARGET, "golden": GOLDEN, "live_oid": live[0],
                        "golden_oid": golden_oid, "system_identifier": str(system_id), "marker": marker,
                        "members": 734, "created_at": datetime.now(timezone.utc).isoformat()}
            save_metadata(metadata_file, metadata)
        else:
            # Fixed identifiers only. This is the explicit destructive operation.
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(TARGET)))
            admin.execute(sql.SQL("CREATE DATABASE {} WITH TEMPLATE {} ALLOW_CONNECTIONS false").format(sql.Identifier(TARGET), sql.Identifier(GOLDEN)))
            admin.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(TARGET)))
            admin.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(TARGET), sql.SQL(",").join(map(sql.Identifier, ROLES))))
            admin.execute(sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS true").format(sql.Identifier(TARGET)))
            database_state(root)
            metadata["live_oid"] = admin.execute("SELECT oid FROM pg_database WHERE datname=%s", (TARGET,)).fetchone()[0]
            metadata["last_reset_at"] = datetime.now(timezone.utc).isoformat()
            save_metadata(metadata_file, metadata, replace=True)
        control_app("start")
        after = wait_and_smoke()
        report.update(passed=bool(after.get("passed")), members=734, smoke=after,
                      golden_connections_disabled=True, existing_preserved=False)
        return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("create", "reset"))
    parser.add_argument("--confirm-target")
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args(argv)
    evidence = args.evidence or ROOT / ("app/evidence/access-control/golden-" + args.command + ".json")
    result = {"passed": False, "command": args.command, "target": TARGET, "reset_test_status": "NOT TESTED"}
    attempted = False
    try:
        if args.command == "reset" and args.confirm_target != TARGET:
            raise ValueError("Explicit --confirm-target protected_734 required")
        settings = Settings.from_env()
        setup_url(settings, os.environ["APP_SETUP_DATABASE_URL"])
        root = external_directory(os.environ["DPR_SECRETS_DIR"])
        directory = external_directory(os.environ["DPR_PRIVATE_DIR"]) / "service-b/pentest"
        attempted = True
        result.update(operate(args.command, root, directory))
        if args.command == "reset": result["reset_test_status"] = "PASSED" if result["passed"] else "FAILED"
    except (Exception, KeyboardInterrupt):
        result.update(passed=False, error="golden_operation_failed_details_withheld", app_state="inspect_or_keep_maintenance")
        if attempted and args.command == "reset": result["reset_test_status"] = "FAILED"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "command": args.command, "report": str(evidence)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
