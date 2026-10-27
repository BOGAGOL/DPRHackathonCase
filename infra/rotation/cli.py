"""python -m infra.rotation: explicit prepare, then rotate or resume."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from uuid import uuid4

from infra.postgres.credentials import load_password
from infra.protected.credentials import role_password
from infra.security import REPO, external_directory
from infra.targets import PROTECTED_DATABASES
from migration.connection import connection_parameters
from .runner import execute, prepare
from .worker import RotationError


def runtime_parameters(database, role, local=False):
    if role not in {"admin_user", "scanner_user", "bootstrap"}: raise RotationError("invalid_runtime_role")
    root = external_directory(os.environ.get("DPR_SECRETS_DIR")) if local else None
    if local and not os.environ.get("PGSSLROOTCERT"):
        os.environ["PGSSLROOTCERT"] = str(root/"postgres/tls/ca.crt")
    if role == "bootstrap":
        user = os.environ.get("DPR_ROTATION_BOOTSTRAP_USER", "postgres")
        password = os.environ.get("DPR_ROTATION_BOOTSTRAP_PASSWORD")
        if local and not password: password = load_password(root)
    else:
        user = role; password = os.environ.get("DPR_"+role.upper()+"_PASSWORD")
        if local and not password: password = role_password(root, role)
    if not password: raise RotationError("missing_database_credential")
    return connection_parameters(database, user=user, password=password)


def write_report(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+"."+uuid4().hex+".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    temporary.replace(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-credentials", action="store_true", help="Explicit Windows DPAPI DB credentials; tokens still from env")
    parser.add_argument("--evidence-dir", type=Path, default=REPO/"evidence/keys")
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("prepare")
    command.add_argument("--database", choices=PROTECTED_DATABASES, required=True)
    command = commands.add_parser("rotate")
    command.add_argument("--database", choices=PROTECTED_DATABASES, action="append", required=True)
    command.add_argument("--batch-size", type=int, default=100)
    command.add_argument("--resume-version", type=int)
    command.add_argument("--max-batches", type=int, help="Pause after bounded batches; resume with the SAME target version")
    args = parser.parse_args(argv)
    path = args.evidence_dir/("prepare-"+args.database+".json" if args.command == "prepare" else "rotation.json")
    report = {"schema_version": 1, "passed": False, "status": "starting", "checked_at_utc": datetime.now(timezone.utc).isoformat()}
    try:
        if args.command == "prepare":
            report = prepare(runtime_parameters(args.database, "bootstrap", args.local_credentials))
        else:
            writer = runtime_parameters(args.database[0], "admin_user", args.local_credentials)
            reader = runtime_parameters(args.database[0], "scanner_user", args.local_credentials)
            report = execute(args.database, writer, reader, batch_size=args.batch_size,
                resume_version=args.resume_version, max_batches=args.max_batches,
                checkpoint=lambda state: (report.update(state), write_report(path, state)))
        write_report(path, report)
        success = report.get("passed") or report.get("status") == "paused"
        print(json.dumps({"passed": report.get("passed"), "status": report.get("status", "prepared"),
            "target_version": report.get("target_version"), "report": str(path)}))
        return 0 if success else 1
    except (Exception, KeyboardInterrupt):
        # Preserve checkpoint/target after partial commit or ambiguous rotation.
        report.update(passed=False, status="failed", error="rotation_failed_details_withheld")
        write_report(path, report)
        print(json.dumps({"passed": False, "error": "rotation_failed_details_withheld",
            "target_version": report.get("target_version"), "report": str(path),
            "recovery": "Inspect target_version and key metadata; resume with the same version. Never retry rotate blindly."}))
        return 1
