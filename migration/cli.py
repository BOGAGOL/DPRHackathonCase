"""Windows-friendly CLI. Env credentials only; error payloads never reach output."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from dprcrypto import OpenBaoClient
from infra.openbao.api import from_environment
from infra.openbao.init import revoke_migration
from infra.protected.apply import load_profile
from infra.security import REPO
from .connection import connection_parameters
from .model import MigrationError
from .prepare import prepare
from .runner import PAIRS, check_pair, execute


def write_report(name: str, report: dict) -> None:
    directory = REPO/"evidence/migration"
    directory.mkdir(parents=True,exist_ok=True)
    destination = directory/(name+".json")
    temporary = directory/(name+"."+uuid4().hex+".tmp")
    temporary.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    # Windows can briefly deny rename while another process replaces/reads the
    # canonical report. Unique temp files + bounded retry retain atomic JSON.
    for attempt in range(10):
        try:
            temporary.replace(destination)
            break
        except PermissionError:
            if attempt==9:
                raise
            time.sleep(0.01*(attempt+1))


def runtime_parameters(database: str, *, source: bool) -> dict:
    if source:
        user = os.environ.get("DPR_SOURCE_USER") or os.environ.get("PGUSER")
        password = os.environ.get("DPR_SOURCE_PASSWORD") or os.environ.get("PGPASSWORD")
    else:
        user = "migration_user"
        password = os.environ.get("DPR_MIGRATION_USER_PASSWORD")
        if not password:
            raise MigrationError("missing_target_credential")
    params = connection_parameters(database,source=source,user=user,password=password)
    if not source:
        params["options"] = "-c lock_timeout=5s"
    return params


def revoke() -> dict:
    # This API validates the token has only svc-migration before revoke-self.
    token = os.environ.get("OPENBAO_MIGRATION_TOKEN", "")
    if not token:
        raise MigrationError("missing_migration_token")
    revoke_migration(from_environment(),token)
    return {"passed":True,"migration_token_revoked":True}


def check_dependencies(source_name: str, target_name: str, profile_path: Path) -> dict:
    check_pair(source_name,target_name)
    load_profile(profile_path)
    checks = {"profile_current":True}
    # No writes, no automatic init/unseal, and no secret values in this report.
    state = from_environment().request("/sys/seal-status")
    checks["openbao_initialized"] = bool(state["initialized"])
    checks["openbao_unsealed"] = not state["sealed"]
    checks["migration_token_present"] = bool(os.environ.get("OPENBAO_MIGRATION_TOKEN"))
    checks["validation_token_present"] = bool(os.environ.get("OPENBAO_VALIDATION_TOKEN"))
    for label,token_env,policy in (("migration","OPENBAO_MIGRATION_TOKEN","svc-migration"),
                                   ("validation","OPENBAO_VALIDATION_TOKEN","svc-app")):
        checks[label+"_policy_valid"] = False
        if checks["openbao_initialized"] and checks["openbao_unsealed"] and checks[label+"_token_present"]:
            try:
                with OpenBaoClient(token_env=token_env) as client:
                    client.require_policy(policy)
                checks[label+"_policy_valid"] = True
            except Exception:
                pass
    for label,database,is_source in (("source",source_name,True),("target",target_name,False)):
        try:
            with psycopg.connect(**runtime_parameters(database,source=is_source),autocommit=True) as connection:
                actual,version = connection.execute("SELECT current_database(),current_setting('server_version_num')::int").fetchone()
                checks[label+"_tls_connection"] = actual==database and version//10000==18
                if is_source:
                    checks["source_read_only"] = connection.execute("SHOW transaction_read_only").fetchone()[0]=="on"
                else:
                    checks["target_control_table"] = connection.execute("SELECT to_regclass('public.migration_jobs') IS NOT NULL").fetchone()[0]
                    checks["target_migration_login"] = connection.execute("SELECT current_user='migration_user' AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication FROM pg_roles WHERE rolname=current_user").fetchone()[0]
        except Exception:
            checks[label+"_tls_connection"] = False
    return {"passed":all(checks.values()),"checks":checks,"data_migrated":False,"source":source_name,"target":target_name}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command",required=True)
    for name in ("run","validate","check"):
        command = subparsers.add_parser(name)
        command.add_argument("--source",choices=tuple(PAIRS),required=True)
        command.add_argument("--target",choices=tuple(PAIRS.values()),required=True)
        command.add_argument("--profile",type=Path,default=REPO/"policy/protection_profile.yaml")
        if name=="run":
            command.add_argument("--batch-size",type=int,default=1000)
            command.add_argument("--max-batches",type=int)
            command.add_argument("--keep-migration-token",action="store_true")
    command = subparsers.add_parser("prepare")
    command.add_argument("--target",choices=tuple(PAIRS.values()),required=True)
    command.add_argument("--profile",type=Path,default=REPO/"policy/protection_profile.yaml")
    command.add_argument("--create-local-credentials",action="store_true")
    subparsers.add_parser("revoke")
    args = parser.parse_args()
    report = {"schema_version":1,"passed":False,"command":args.command,"checked_at_utc":datetime.now(timezone.utc).isoformat()}
    name = {"run":"validation","validate":"validation","check":"readiness","prepare":"prepare","revoke":"revocation"}[args.command]
    try:
        if args.command=="prepare":
            report.update(prepare(args.target,args.profile,create_local_credentials=args.create_local_credentials))
        elif args.command=="revoke":
            report.update(revoke())
        elif args.command=="check":
            report.update(check_dependencies(args.source,args.target,args.profile))
        else:
            check_pair(args.source,args.target)
            profile = load_profile(args.profile)
            with OpenBaoClient(token_env="OPENBAO_MIGRATION_TOKEN") as migration_client, \
                 OpenBaoClient(token_env="OPENBAO_VALIDATION_TOKEN") as validation_client, \
                 psycopg.connect(**runtime_parameters(args.source,source=True),autocommit=True,row_factory=dict_row) as source, \
                 psycopg.connect(**runtime_parameters(args.target,source=False),autocommit=True,row_factory=dict_row) as target:
                report.update(execute(source,target,source_name=args.source,target_name=args.target,profile=profile,
                    profile_hash=hashlib.sha256(args.profile.read_bytes()).hexdigest(),migration_client=migration_client,
                    validation_client=validation_client,batch_size=getattr(args,"batch_size",1000),
                    max_batches=getattr(args,"max_batches",None),validate_only=args.command=="validate",
                    expected_rows=734 if args.source=="postgres" else 100000))
            if args.command=="run" and report.get("complete") and not args.keep_migration_token:
                revocation = {**revoke(),"schema_version":1,"checked_at_utc":datetime.now(timezone.utc).isoformat()}
                write_report("revocation",revocation)
                report["migration_token_revoked"] = True
    except MigrationError as error:
        report.update(passed=False,error=error.code)
    except (Exception, KeyboardInterrupt):
        # No driver/OpenBao exception text, SQL parameters, traceback or row identity.
        report.update(passed=False,error="migration_operation_failed_details_withheld")
    if args.command=="run" and report.get("status")=="paused":
        name = "progress"
    if getattr(args,"target",None):
        report["target"] = args.target
        write_report(name+"-"+args.target,report)
    write_report(name,report)
    success = report["passed"] or report.get("status")=="paused"
    print("Migration "+args.command+": "+("PAUSED" if report.get("status")=="paused" else "PASS" if success else "FAIL (details withheld)"))
    if not success:
        raise SystemExit(1)


if __name__=="__main__":
    main()
