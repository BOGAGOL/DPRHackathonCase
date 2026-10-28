"""Synthetic principals/rows only, isolated PostgreSQL 18; never pg-dpr data."""

import base64
from datetime import datetime,timezone
import json
import os
import secrets
import subprocess
import time
from uuid import uuid4

from argon2 import PasswordHasher
import psycopg
import pytest

from dprcrypto import encrypt
from infra.protected.apply import inspect_schema,load_profile,provision
from infra.protected.credentials import ROLES
from infra.security import REPO


@pytest.mark.skipif(os.environ.get("DPR_SCHEMA_INTEGRATION")!="1",reason="Set DPR_SCHEMA_INTEGRATION=1 for isolated PG18 role/RLS test")
def test_contract_schema_least_privilege_rls_audit_backup_and_idempotence(tmp_path):
    project="dpr-schema-test-"+secrets.token_hex(5)
    password=secrets.token_urlsafe(36)
    environment={**os.environ,"DPR_POSTGRES_PORT":"0","DPR_POSTGRES_PASSWORD":password}
    command=["docker","compose","-p",project,"-f",str(REPO/"infra/tests/compose.postgres.yaml")]
    def compose(*args):
        result=subprocess.run(command+list(args),env=environment,capture_output=True,text=True,timeout=180)
        if result.returncode: raise RuntimeError("Disposable schema fixture failed; output withheld")
        return result.stdout.strip()
    report={"schema_version":1,"passed":False,"scope":"disposable PG18, synthetic fixture only","checks":{}}
    checks=report["checks"]
    try:
        compose("up","-d","postgres")
        container=project+"-postgres-1"
        port=int(compose("port","postgres","5432").rsplit(":",1)[1])
        params={"host":"127.0.0.1","port":port,"user":"dpr_bootstrap","password":password,"dbname":"dpr_lab","connect_timeout":3,"sslmode":"disable"}
        for _ in range(60):
            try:
                with psycopg.connect(**params,autocommit=True) as connection:
                    connection.execute("CREATE DATABASE protected_734")
                break
            except psycopg.OperationalError: time.sleep(0.5)
        else: raise RuntimeError("Isolated PostgreSQL not ready")
        params["dbname"]="protected_734"
        profile=load_profile(REPO/"policy/protection_profile.yaml")
        passwords={role:secrets.token_urlsafe(36) for role in ROLES}
        provision(container,"protected_734","dpr_bootstrap",passwords,profile)
        checks.update(inspect_schema(params,profile)["checks"])
        fixture=json.loads((REPO/"policy/synthetic_scope_fixture.json").read_text())
        principal_a,principal_b=[item["user_id"] for item in fixture["principals"]]
        record_a,record_b=[item["anggota_id"] for item in fixture["records"]]
        wrapped="vault:v1:"+base64.b64encode(os.urandom(60)).decode()
        def row_values(identity,legacy):
            return (identity,legacy,1,wrapped,wrapped,encrypt("SYNTHETIC",os.urandom(32),column="nama",anggota_id=identity),"L","Synthetic Job","Synthetic Office","Synthetic Bank","40-49")
        insert="""INSERT INTO public.anggota_protected(anggota_id,legacy_row_id,protection_version,dek_pii_wrapped,dek_fin_wrapped,nama_ct,jenis_kelamin,pekerjaan_terakhir,nama_kppn,nama_bank,age_band)
                  VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
        with psycopg.connect(**params,autocommit=True) as admin:
            hasher=PasswordHasher(time_cost=3,memory_cost=65536,parallelism=2)
            for user in fixture["principals"]:
                admin.execute("INSERT INTO public.app_users(user_id,username,password_hash,role) VALUES(%s,%s,%s,%s)",
                              (user["user_id"],user["username"],hasher.hash(secrets.token_urlsafe(32)),user["role"]))
            for row in fixture["records"]: admin.execute(insert,row_values(row["anggota_id"],row["legacy_row_id"]))
            for scope in fixture["scopes"]:
                admin.execute("INSERT INTO public.access_scope(principal,anggota_id,permission,source_label) VALUES(%s,%s,%s,%s)",
                              (scope["principal"],scope["anggota_id"],scope["permission"],scope["source_label"]))
        def connect(role): return psycopg.connect(**{**params,"user":role,"password":passwords[role]},autocommit=True)
        def denied(role,statement,values=None):
            with connect(role) as connection:
                try: connection.execute(statement,values);return False
                except psycopg.errors.InsufficientPrivilege:return True
        with connect("app_user") as app:
            checks["missing_principal_denied"]=app.execute("SELECT count(*) FROM public.anggota_protected").fetchone()[0]==0
            app.execute("SELECT set_config('app.principal',%s,false)",("invalid",))
            checks["invalid_principal_denied"]=app.execute("SELECT count(*) FROM public.anggota_protected").fetchone()[0]==0
            app.execute("SELECT set_config('app.principal',%s,false)",(principal_a,))
            checks["principal_a_scope"]=[str(row[0]) for row in app.execute("SELECT anggota_id FROM public.anggota_protected")]==[record_a]
            checks["own_scope_metadata_only"]=app.execute("SELECT count(*) FROM public.access_scope WHERE principal<>%s",(principal_a,)).fetchone()[0]==0
            checks["other_record_update_filtered"]=app.execute("UPDATE public.anggota_protected SET age_band=%s WHERE anggota_id=%s",("50-59",record_b)).rowcount==0
            checks["authorized_update"]=app.execute("UPDATE public.anggota_protected SET age_band=%s WHERE anggota_id=%s",("50-59",record_a)).rowcount==1
            new_id=str(uuid4())
            app.execute(insert,row_values(new_id,3))
            checks["authorized_insert_creator_scope"]=app.execute("SELECT count(*) FROM public.anggota_protected WHERE anggota_id=%s",(new_id,)).fetchone()[0]==1
            app.execute("SELECT set_config('app.principal',%s,false)",(principal_b,))
            checks["context_spoof_limitation_demonstrated"]=[str(row[0]) for row in app.execute("SELECT anggota_id FROM public.anggota_protected")]==[record_b]
            try: app.execute(insert,row_values(str(uuid4()),4));checks["unauthorized_insert_denied"]=False
            except psycopg.errors.InsufficientPrivilege:checks["unauthorized_insert_denied"]=True
        with connect("app_user") as app:
            with app.transaction():
                app.execute("SELECT set_config('app.principal',%s,true)",(principal_a,))
                checks["transaction_local_scope"]=app.execute("SELECT count(*) FROM public.anggota_protected").fetchone()[0]==2
            checks["local_scope_does_not_leak_to_next_transaction"]=app.execute("SELECT count(*) FROM public.anggota_protected").fetchone()[0]==0
        checks["app_no_scope_write"]=denied("app_user","INSERT INTO public.access_scope(principal,anggota_id,permission) VALUES(%s,%s,'read')",(principal_a,record_b))
        checks["app_no_delete"]=denied("app_user","DELETE FROM public.anggota_protected")
        for role in ROLES:
            checks[role+":no_ddl"]=denied(role,"CREATE TABLE public.forbidden_probe(id int)")
            checks[role+":no_owner_membership"]=denied(role,"SET ROLE schema_owner")
        for role in ("analyst_user","auditor_user","admin_user"):
            checks[role+":no_raw_member_read"]=denied(role,"SELECT * FROM public.anggota_protected")
        checks["analyst_no_per_record_view"]=denied("analyst_user","SELECT * FROM public.analyst_view")
        with connect("analyst_user") as analyst:
            checks["analyst_small_groups_absent"]=analyst.execute("SELECT * FROM public.analyst_summary").fetchall()==[]
            checks["analyst_aggregate_function_suppressed"]=analyst.execute("SELECT * FROM public.analyst_age_summary()").fetchall()==[]
        checks["analyst_no_auth_hashes"]=denied("analyst_user","SELECT password_hash FROM public.app_users")
        with connect("auditor_user") as auditor:checks["auditor_can_read_audit"]=auditor.execute("SELECT count(*) FROM public.audit_log").fetchone()[0]>0
        checks["auditor_no_audit_mutation"]=denied("auditor_user","DELETE FROM public.audit_log")
        checks["app_no_audit_mutation"]=denied("app_user","UPDATE public.audit_log SET action='forged'")
        with connect("scanner_user") as scanner: checks["scanner_reads_ciphertext_rows"]=scanner.execute("SELECT count(*) FROM public.anggota_protected").fetchone()[0]==3
        checks["scanner_no_write"]=denied("scanner_user","UPDATE public.anggota_protected SET age_band='30-39'")
        with connect("migration_user") as migration: checks["migration_reads_all_rows"]=migration.execute("SELECT count(*) FROM public.anggota_protected").fetchone()[0]==3
        checks["migration_no_auth_hashes"]=denied("migration_user","SELECT password_hash FROM public.app_users")
        with connect("admin_user") as manager:
            manager.execute("UPDATE public.app_users SET active=false WHERE user_id=%s",(principal_b,))
        with connect("app_user") as app:
            app.execute("SELECT set_config('app.principal',%s,false)",(principal_b,))
            checks["inactive_principal_denied"]=app.execute("SELECT count(*) FROM public.anggota_protected").fetchone()[0]==0
        with connect("admin_user") as manager:
            manager.execute("UPDATE public.app_users SET active=true WHERE user_id=%s",(principal_b,))
            manager.execute("INSERT INTO public.access_scope(principal,anggota_id,permission,source_label) VALUES(%s,%s,'read','synthetic')",(principal_b,record_a))
            checks["admin_scope_change_audited"]=manager.execute("SELECT count(*) FROM public.audit_log WHERE action='access_scope.insert' AND database_user='admin_user'").fetchone()[0]>0
        with psycopg.connect(**params,autocommit=True) as admin:
            for label,query,values in [
                ("reject_plaintext_password","UPDATE public.app_users SET password_hash=%s WHERE user_id=%s",(secrets.token_urlsafe(32),principal_a)),
                ("reject_invalid_ciphertext","UPDATE public.anggota_protected SET nama_ct=%s WHERE anggota_id=%s",(b"synthetic-invalid",record_a)),
                ("reject_invalid_blind_index","UPDATE public.anggota_protected SET email_bidx=%s WHERE anggota_id=%s",(os.urandom(31),record_a)),
            ]:
                try:admin.execute(query,values);checks[label]=False
                except psycopg.errors.CheckViolation:checks[label]=True
        # pg_dump defaults row_security=off; use the documented RLS-safe full-read policy.
        dump=subprocess.run(["docker","exec","--user","postgres",container,"pg_dump","-U","dpr_bootstrap","--role=backup_user",
            "--enable-row-security","--format=custom","--no-owner","--no-acl","protected_734"],capture_output=True,timeout=60)
        checks["backup_pg_dump_with_rls"]=dump.returncode==0 and dump.stdout.startswith(b"PGDMP")
        with psycopg.connect(**{**params,"dbname":"dpr_lab"},autocommit=True) as admin:
            admin.execute("CREATE DATABASE protected_100k")
        restore=subprocess.run(["docker","exec","-i","--user","postgres",container,"pg_restore","-U","dpr_bootstrap",
            "--exit-on-error","--no-owner","--no-acl","-d","protected_100k"],input=dump.stdout,capture_output=True,timeout=60)
        with psycopg.connect(**{**params,"dbname":"protected_100k"},autocommit=True) as restored:
            checks["backup_restores_all_rows"]=restore.returncode==0 and restored.execute("SELECT count(*) FROM public.anggota_protected").fetchone()[0]==3
        with psycopg.connect(**params,autocommit=True) as admin:
            hashes=admin.execute("SELECT rolname,rolpassword FROM pg_authid WHERE rolname=ANY(%s) ORDER BY rolname",(list(ROLES),)).fetchall()
            count=admin.execute("SELECT count(*) FROM public.anggota_protected").fetchone()[0]
            admin.execute("GRANT CREATE ON SCHEMA public TO app_user")
            admin.execute("GRANT CREATE,TEMP ON DATABASE protected_734 TO app_user")
        provision(container,"protected_734","dpr_bootstrap",passwords,profile)
        with psycopg.connect(**params,autocommit=True) as admin:
            checks["idempotence_preserves_rows"]=admin.execute("SELECT count(*) FROM public.anggota_protected").fetchone()[0]==count
            checks["idempotence_preserves_passwords"]=hashes==admin.execute("SELECT rolname,rolpassword FROM pg_authid WHERE rolname=ANY(%s) ORDER BY rolname",(list(ROLES),)).fetchall()
            checks["reapply_removes_direct_ddl_grants"]=not any(admin.execute("SELECT has_schema_privilege('app_user','public','CREATE'),has_database_privilege('app_user','protected_734','CREATE'),has_database_privilege('app_user','protected_734','TEMP')").fetchone())
            admin.execute("SET ROLE schema_owner")
            admin.execute("CREATE FUNCTION public.default_privilege_probe() RETURNS int LANGUAGE sql AS 'SELECT 1'")
            admin.execute("RESET ROLE")
            checks["future_functions_not_public"]=not admin.execute("SELECT has_function_privilege('app_user','public.default_privilege_probe()','EXECUTE')").fetchone()[0]
            admin.execute("ALTER ROLE app_user BYPASSRLS")
        try:
            provision(container,"protected_734","dpr_bootstrap",passwords,profile)
            checks["unsafe_existing_role_rejected"]=False
        except RuntimeError:checks["unsafe_existing_role_rejected"]=True
        with psycopg.connect(**params,autocommit=True) as admin:
            admin.execute("ALTER ROLE app_user NOBYPASSRLS")
        try:
            provision(container,"protected_734","dpr_bootstrap",passwords,profile,system_identifier="1")
            checks["wrong_cluster_rejected"]=False
        except RuntimeError:checks["wrong_cluster_rejected"]=True
        report["passed"]=all(checks.values())
        if not report["passed"]:pytest.fail("Protected schema checks failed: "+", ".join(name for name,passed in checks.items() if not passed),pytrace=False)
    finally:
        report["checked_at_utc"]=datetime.now(timezone.utc).isoformat()
        path=REPO/"evidence/schema/integration.json";path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
        compose("down","--volumes","--remove-orphans")
