"""PowerShell-friendly CLI. Keys/passwords are accepted only through environment."""

import argparse
import json
import os
from pathlib import Path

from infra.security import REPO, external_directory
from infra.targets import PROTECTED_DATABASES
from .crypto import BackupError
from .drills import retention_test, tamper_test
from .runner import backup, restore
from .settings import artifact_store, backup_keys, local_keys, parameters


def parser():
    root = argparse.ArgumentParser(description="PG18 encrypted streaming backup and fresh restore")
    root.add_argument("--local-credentials", action="store_true", help="Explicit Windows DPAPI development convenience")
    root.add_argument("--container", default="pg-dpr")
    root.add_argument("--evidence-dir", type=Path, default=REPO/"evidence/backup")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init-keys", help="Create independent backup keys outside Git using Windows DPAPI")
    command = commands.add_parser("backup")
    command.add_argument("--source", choices=PROTECTED_DATABASES, required=True)
    command.add_argument("--retention-days", type=int, default=30)
    command.add_argument("--output-dir", default=os.environ.get("DPR_BACKUP_DIR"))
    command = commands.add_parser("restore")
    command.add_argument("--manifest", type=Path, required=True)
    command.add_argument("--target", help="New dpr_restore_<32 lowercase hex> database; default random")
    command.add_argument("--with-openbao", action="store_true")
    command.add_argument("--sample-size", type=int, default=16)
    command = commands.add_parser("tamper-test")
    command.add_argument("--manifest", type=Path, required=True)
    command = commands.add_parser("retention-test")
    command.add_argument("--manifest", type=Path, required=True)
    command.add_argument("--output-dir", default=os.environ.get("DPR_BACKUP_DIR"))
    command.add_argument("--retention-days", type=int, default=30)
    return root


def write_report(directory, filename, result):
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory/(filename+".tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    temporary.replace(directory/filename)


def main(argv=None):
    args = parser().parse_args(argv)
    filenames = {"init-keys": "key-setup.json", "backup": "backup-report.json", "restore": "restore-report.json",
                 "tamper-test": "tamper.json", "retention-test": "retention.json"}
    filename = filenames[args.command]
    try:
        if args.command == "init-keys":
            local_keys(external_directory(os.environ.get("DPR_SECRETS_DIR")), create=True)
            result = {"schema_version": 1, "passed": True, "keys_separate_from_data_domains": True,
                      "manifest_key_separate": True, "storage": "Windows DPAPI outside repository"}
        else:
            keys = local_keys(external_directory(os.environ.get("DPR_SECRETS_DIR"))) if args.local_credentials else backup_keys()
            if args.command == "backup":
                result = backup(args.source, parameters(args.source, local=args.local_credentials), keys,
                    artifact_store(args.output_dir), container=args.container, retention_days=args.retention_days)
                result["passed"] = True
            elif args.command == "restore":
                result = restore(args.manifest, parameters("postgres", admin=True, local=args.local_credentials), keys,
                    container=args.container, database=args.target, with_openbao=args.with_openbao, sample_size=args.sample_size)
            elif args.command == "tamper-test":
                result = tamper_test(args.manifest, parameters("postgres", admin=True, local=args.local_credentials), keys, container=args.container)
            else:
                result = retention_test(args.manifest, parameters("postgres", admin=True, local=args.local_credentials),
                    parameters("protected_734", local=args.local_credentials), keys, artifact_store(args.output_dir),
                    container=args.container, retention_days=args.retention_days)
        write_report(args.evidence_dir, filename, result)
        print(json.dumps({"passed": True, "report": str(args.evidence_dir/filename),
                         **{key: result[key] for key in ("artifact_id", "manifest", "database", "source_rows", "size_bytes") if key in result}}))
        return 0
    except Exception as error:
        safe_codes = {"encrypted_artifact_digest_mismatch", "manifest_authentication_failed", "invalid_manifest",
            "artifact_authentication_failed", "restore_requires_reserved_new_database_name", "unsafe_backup_role",
            "two_distinct_32_byte_backup_keys_required", "restore_requires_preprovisioned_safe_contract_roles",
            "unexpected_public_tables", "restored_security_validation_failed", "restored_row_count_mismatch"}
        code = str(error) if isinstance(error, BackupError) and str(error) in safe_codes else "backup_operation_failed_details_withheld"
        write_report(args.evidence_dir, filename, {"schema_version": 1, "passed": False, "error": code})
        print(json.dumps({"passed": False, "error": code, "report": str(args.evidence_dir/filename)}))
        return 1
