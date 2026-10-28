"""Upgrade only the analyst interface; never bootstrap roles or migrate data."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re

import psycopg

from infra.security import REPO
from infra.targets import PROTECTED_DATABASES


def security_checks(connection):
    """Check effective access, including column grants and PUBLIC privileges."""
    isolated = connection.execute("""SELECT NOT EXISTS (
        SELECT 1 FROM pg_class c WHERE c.relnamespace='public'::regnamespace
        AND c.relkind IN ('r','p','v','m','f') AND c.oid<>'public.analyst_summary'::regclass
        AND (has_table_privilege('analyst_user',c.oid,'SELECT')
             OR has_any_column_privilege('analyst_user',c.oid,'SELECT')))""").fetchone()[0]
    owner, options = connection.execute("SELECT pg_get_userbyid(relowner),reloptions FROM pg_class WHERE oid='public.analyst_summary'::regclass").fetchone()
    columns = connection.execute("SELECT attname,atttypid::regtype::text FROM pg_attribute WHERE attrelid='public.analyst_summary'::regclass AND attnum>0 AND NOT attisdropped ORDER BY attnum").fetchall()
    return {
        "analyst_no_per_record_select": bool(isolated),
        "analyst_can_select_aggregate": connection.execute("SELECT has_table_privilege('analyst_user','public.analyst_summary','SELECT')").fetchone()[0],
        "analyst_aggregate_owner_and_barrier": owner == "schema_owner" and "security_barrier=true" in (options or []) and "security_invoker=false" in (options or []),
        "analyst_aggregate_contract_columns": columns == [("dimension", "text"), ("value", "text"), ("anggota_count", "bigint")],
    }


def upgrade(connection):
    """Apply the canonical SQL inside the caller's transaction, including restores."""
    connection.execute("SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='60s'")
    connection.execute((REPO/"sql/protected/03_analyst_suppression.sql").read_text(encoding="utf-8"), prepare=False)
    checks = security_checks(connection)
    if not all(checks.values()):
        raise ValueError("Analyst suppression verification failed")
    return checks


def parameters(database):
    """Credentials stay in environment; production connections always verify TLS."""
    if database not in PROTECTED_DATABASES and not re.fullmatch(r"dpr_restore_[0-9a-f]{32}", database):
        raise ValueError("Only protected databases may be upgraded")
    if os.environ.get("PGSSLMODE", "verify-full") != "verify-full":
        raise ValueError("Verified TLS is required")
    return {"dbname":database,"host":os.environ.get("PGHOST","127.0.0.1"),
        "port":int(os.environ.get("PGPORT","5433")),"user":os.environ["PGUSER"],
        "password":os.environ["PGPASSWORD"],"sslrootcert":os.environ["PGSSLROOTCERT"],
        "sslmode":"verify-full","gssencmode":"disable","connect_timeout":5,
        "options":"-c log_statement=none -c log_min_error_statement=panic -c log_parameter_max_length_on_error=0"}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--evidence",type=Path,default=REPO/"evidence/access-control/analyst-upgrade.json")
    args=parser.parse_args(argv)
    report={"schema_version":1,"passed":False,"checked_at_utc":datetime.now(timezone.utc).isoformat(),
        "mode":"verify" if args.verify_only else "apply","member_data_modified":False}
    try:
        with psycopg.connect(**parameters(args.database)) as connection:
            if args.verify_only: connection.execute("SET TRANSACTION READ ONLY")
            checks=security_checks(connection) if args.verify_only else upgrade(connection)
            report.update(checks=checks,passed=all(checks.values()))
    except Exception:
        report["passed"]=False
        report["error"]="analyst_upgrade_failed_details_withheld"
    args.evidence.parent.mkdir(parents=True,exist_ok=True)
    args.evidence.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"passed":report["passed"],"report":str(args.evidence)}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
