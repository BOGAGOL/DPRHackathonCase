"""Provision only allowlisted protected databases on the existing pg-dpr, atomically."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

import psycopg
from psycopg import sql
import yaml

from infra.postgres.development import parameters as local_admin_parameters
from infra.protected.credentials import ROLES, role_environment, role_password
from infra.protected.analyst import security_checks
from infra.security import REPO, external_directory
from infra.targets import PROTECTED_DATABASES
from policy.build_profile import build, text_hashes


DATABASES = PROTECTED_DATABASES
REF = ("jenis_kelamin", "pekerjaan_terakhir", "nama_kppn", "nama_bank", "age_band")


def load_profile(path: Path) -> dict:
    profile = yaml.safe_load(path.read_text(encoding="utf-8"))
    inventory = REPO / profile["provenance"]["inventory"]
    rebuilt = build(inventory, REPO / "policy/overrides.yaml", REPO / "docs/contracts/CONTRACT.md")
    for key,input_path in (("inventory_sha256",inventory),("overrides_sha256",REPO/"policy/overrides.yaml"),
                           ("contract_sha256",REPO/"docs/contracts/CONTRACT.md")):
        if profile["provenance"][key] not in text_hashes(input_path):
            raise ValueError("Protection profile inputs changed")
        rebuilt["provenance"][key] = profile["provenance"][key]
    if profile != rebuilt:
        raise ValueError("Protection profile is stale or conflicts with its declared inputs")
    return profile


def schema_check_sql(profile: dict) -> str:
    expected = sorted(value["storage_column"] for value in profile["columns"].values() if value["aead"])
    # Metadata-only assertion stays inside the provisioning transaction.
    return sql.SQL("""DO $check$
DECLARE actual text[];
BEGIN
  SELECT array_agg(attname::text ORDER BY attname) INTO actual FROM pg_attribute
    WHERE attrelid='public.anggota_protected'::regclass AND attnum>0 AND NOT attisdropped
      AND right(attname,3)='_ct' AND atttypid='bytea'::regtype;
  IF actual IS DISTINCT FROM {}::text[] THEN RAISE EXCEPTION 'Protected column contract mismatch'; END IF;
  IF EXISTS(SELECT 1 FROM pg_class WHERE relnamespace='public'::regnamespace AND relkind IN ('r','v','S')
      AND relowner<>(SELECT oid FROM pg_roles WHERE rolname='schema_owner'))
    THEN RAISE EXCEPTION 'Unexpected object ownership'; END IF;
END $check$;""").format(sql.Literal(expected)).as_string()


def provision(container: str, database: str, admin_user: str, passwords: dict[str,str], profile: dict,
              *, system_identifier: str | None = None, psql_bin: Path | None = None) -> None:
    if database not in DATABASES or set(passwords) != set(ROLES):
        raise ValueError("Only the declared protected targets and roles may be provisioned")
    if any(len(value) < 20 or "\x00" in value or "\n" in value or "\r" in value for value in passwords.values()):
        raise ValueError("Invalid role credential input")
    roles_sql = (REPO / "sql/roles/01_roles.sql").read_text(encoding="utf-8")
    schema_sql = (REPO / "sql/protected/01_schema.sql").read_text(encoding="utf-8")
    schema_sql += "\n" + (REPO / "sql/protected/02_migration.sql").read_text(encoding="utf-8")
    schema_sql += "\n" + (REPO / "sql/protected/03_analyst_suppression.sql").read_text(encoding="utf-8")
    guard = sql.SQL("""DO $$ BEGIN
IF NOT (current_database()=ANY({}::text[])) OR current_setting('server_version_num')::int/10000<>18
THEN RAISE EXCEPTION 'Wrong protected target/version'; END IF;
IF EXISTS(SELECT 1 FROM pg_class WHERE relnamespace='public'::regnamespace AND relkind IN ('r','v','S')
 AND relowner IS DISTINCT FROM (SELECT oid FROM pg_roles WHERE rolname='schema_owner'))
THEN RAISE EXCEPTION 'Unmanaged existing objects'; END IF; END $$;
""").format(sql.Literal(list(DATABASES))).as_string()
    if system_identifier is not None:
        if not system_identifier.isascii() or not system_identifier.isdecimal():
            raise ValueError("Invalid database cluster identity")
        guard += sql.SQL("DO $$ BEGIN IF (SELECT system_identifier::text FROM pg_control_system()) <> {} THEN RAISE EXCEPTION 'Docker and TLS connection target different clusters'; END IF; END $$;\n").format(sql.Literal(system_identifier)).as_string()
    script = ("\\set ON_ERROR_STOP on\n\\set ECHO none\n\\set VERBOSITY sqlstate\nBEGIN;\n"
        "SET LOCAL log_statement='none'; SET LOCAL log_min_error_statement='panic';\n"
        "SET LOCAL log_parameter_max_length_on_error=0; SET LOCAL lock_timeout='5s';\n"
        "SET LOCAL statement_timeout='60s';\n" + guard +
        "\\set dpr_role_bootstrap_only true\n" + roles_sql + "\n" + schema_sql +
        "\n\\set dpr_role_bootstrap_only false\n" + roles_sql + "\n" + schema_check_sql(profile) + "\nCOMMIT;\n")
    environment = {**os.environ, **{role_environment(role): value for role, value in passwords.items()}}
    command = ["docker"]
    if os.environ.get("DPR_DOCKER_CONTEXT"):
        command += ["--context", os.environ["DPR_DOCKER_CONTEXT"]]
    command += ["exec", "-i", "--user", "postgres"]
    for role in ROLES:
        command += ["--env", role_environment(role)]
    command += [container, "psql", "-X", "-w", "-q", "-v", "ON_ERROR_STOP=1", "-U", admin_user, "-d", database]
    if psql_bin is not None:
        # Explicit local transport for a fresh reproduction cluster. SQL guards,
        # role inputs, transactions and TLS are identical to the container path.
        if not psql_bin.is_absolute() or not psql_bin.is_file():
            raise ValueError("An explicit PostgreSQL psql executable is required")
        if environment.get("PGSSLMODE") != "verify-full" or not Path(environment.get("PGSSLROOTCERT", "")).is_file():
            raise ValueError("Verified native provisioning TLS required")
        command = [str(psql_bin), "-X", "-w", "-q", "-v", "ON_ERROR_STOP=1", "-U", admin_user, "-d", database]
    result = subprocess.run(command, input=script, env=environment, capture_output=True, text=True, timeout=180)
    if result.returncode:
        # Never echo query text: psql variables may have expanded role passwords.
        raise RuntimeError("Protected provisioning failed; transaction rolled back; details withheld")


def inspect_schema(params: dict, profile: dict) -> dict:
    with psycopg.connect(**params) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        columns = dict(connection.execute("SELECT column_name,udt_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s", ("public","anggota_protected")).fetchall())
        expected_ct = {field["storage_column"] for field in profile["columns"].values() if field["aead"]}
        view = [row[0] for row in connection.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position", ("public","analyst_view"))]
        security = connection.execute("SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid=%s::regclass", ("public.anggota_protected",)).fetchone()
        roles = connection.execute("SELECT rolname,rolcanlogin,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=ANY(%s)", (["schema_owner",*ROLES],)).fetchall()
        checks = {"ciphertext_columns": {name for name in columns if name.endswith("_ct")} == expected_ct and all(columns.get(name)=="bytea" for name in expected_ct),
            "no_plaintext_pii_fin": all(name not in columns for name, field in profile["columns"].items() if field["aead"]),
            "blind_index_columns": all(columns.get(name+"_bidx")=="bytea" for name,field in profile["columns"].items() if field["bidx"]),
            "analyst_projection_only": view == list(REF), "rls_enabled_and_forced": security == (True,True),
            "roles_not_privileged": len(roles)==8 and all(not any(row[2:]) for row in roles),
            "owner_nologin": any(row[0]=="schema_owner" and not row[1] for row in roles),
            "service_logins": all(row[1] for row in roles if row[0]!="schema_owner")}
        table_counts = {}
        checks.update(security_checks(connection))
        for name in ("anggota_protected","app_users","access_scope","audit_log"):
            table_counts[name] = connection.execute(sql.SQL("SELECT count(*) FROM public.{}").format(sql.Identifier(name))).fetchone()[0]
        return {"passed": all(checks.values()), "checks": checks, "row_counts": table_counts}


def admin_parameters(root: Path, database: str) -> dict:
    if os.environ.get("PGUSER") and os.environ.get("PGPASSWORD"):
        if os.environ.get("PGPORT", "5433") != "5433":
            raise ValueError("Project database port must be 5433")
        return {"host": os.environ.get("PGHOST","127.0.0.1"), "port":5433, "user":os.environ["PGUSER"],
                "password":os.environ["PGPASSWORD"], "dbname":database, "sslmode":"verify-full", "gssencmode":"disable",
                "sslrootcert":os.environ.get("PGSSLROOTCERT", str(root/"postgres/tls/ca.crt")), "connect_timeout":5}
    return local_admin_parameters(root,database)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", choices=DATABASES, required=True)
    parser.add_argument("--container", default=os.environ.get("DPR_POSTGRES_CONTAINER","pg-dpr"))
    parser.add_argument("--profile", type=Path, default=REPO/"policy/protection_profile.yaml")
    parser.add_argument("--create-local-credentials", action="store_true")
    args = parser.parse_args()
    report = {"schema_version":1, "passed":False, "database":args.database, "data_migrated":False,
              "checked_at_utc":datetime.now(timezone.utc).isoformat()}
    try:
        root = external_directory(os.environ.get("DPR_SECRETS_DIR"))
        profile = load_profile(args.profile)
        params = admin_parameters(root,args.database)
        with psycopg.connect(**params) as connection:
            version, admin, identity = connection.execute("SELECT current_setting('server_version_num')::int,current_user,system_identifier::text FROM pg_control_system()").fetchone()
            if version//10000 != 18:
                raise ValueError("PostgreSQL 18 required")
        passwords = {role:role_password(root,role,create=args.create_local_credentials) for role in ROLES}
        provision(args.container,args.database,admin,passwords,profile,system_identifier=identity)
        report.update(inspect_schema(params,profile), profile_sha256=hashlib.sha256(args.profile.read_bytes()).hexdigest())
    except Exception:
        report["error"] = "protected_schema_setup_failed_details_withheld"
    output = REPO/"evidence/schema"/(args.database+".json")
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print("Protected schema " + args.database + ": " + ("PASS" if report["passed"] else "FAIL"))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
