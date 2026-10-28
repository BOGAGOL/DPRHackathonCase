"""A5 proof using only invented rows and a fresh, isolated PostgreSQL 18 cluster."""

import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time
from types import SimpleNamespace
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest

from infra.protected import analyst, apply
from infra.protected.credentials import ROLES, role_environment
from infra.security import REPO, secure_directory, write_private
from scripts.backup.postgres import check_restored_security


@pytest.fixture(scope="module")
def analyst_lab(tmp_path_factory):
    native=os.environ.get("DPR_NATIVE_PG_BIN")
    if not native and os.environ.get("DPR_ANALYST_INTEGRATION")!="1":
        pytest.skip("Set DPR_ANALYST_INTEGRATION=1 (Docker) or DPR_NATIVE_PG_BIN (native PG18)")
    root=secure_directory(tmp_path_factory.mktemp("analyst-pg18"))
    password=secrets.token_urlsafe(36)
    role_passwords={role:secrets.token_urlsafe(36) for role in ROLES}
    environment={**os.environ,"DPR_POSTGRES_PASSWORD":password,"DPR_POSTGRES_PORT":"0",
        **{role_environment(role):value for role,value in role_passwords.items()}}
    started=False
    def run(command,*,silent=False,**kwargs):
        # pg_ctl's Windows child can inherit captured pipe handles even with -l.
        # DEVNULL avoids waiting forever for a live server to close those pipes.
        output={"stdout":subprocess.DEVNULL,"stderr":subprocess.DEVNULL} if silent else {"capture_output":True}
        result=subprocess.run(command,text=True,timeout=180,**output,**kwargs)
        if result.returncode: raise RuntimeError("Isolated PG18 command failed; output withheld")
        return result
    project="dpr-analyst-test-"+secrets.token_hex(5)
    compose=["docker","compose","-p",project,"-f",str(REPO/"infra/tests/compose.postgres.yaml")]
    try:
        if native:
            binary=Path(native)
            version=run([str(binary/"postgres.exe" if os.name=="nt" else binary/"postgres"),"--version"]).stdout
            if " 18." not in version: raise RuntimeError("Native lab must use PostgreSQL 18")
            def executable(name): return str(binary/(name+(".exe" if os.name=="nt" else "")))
            data=root/"cluster"; password_file=root/"init-password"
            write_private(password_file,(password+"\n").encode())
            try:
                run([executable("initdb"),"-D",str(data),"-U","dpr_bootstrap","--encoding=UTF8","--locale=C",
                    "--auth-host=scram-sha-256","--auth-local=scram-sha-256","--pwfile="+str(password_file)])
            finally: password_file.unlink(missing_ok=True)
            with socket.socket() as listener:
                listener.bind(("127.0.0.1",0)); port=listener.getsockname()[1]
            started=True
            run([executable("pg_ctl"),"-D",str(data),"-l",str(root/"postgres.log"),"-w","start","-o",
                f"-h 127.0.0.1 -p {port} -c log_statement=none -c log_min_error_statement=panic -c log_parameter_max_length_on_error=0"],silent=True)
            container="native-isolated-fixture"
        else:
            run(compose+["up","-d","postgres"],env=environment); started=True
            port=int(run(compose+["port","postgres","5432"],env=environment).stdout.strip().rsplit(":",1)[1])
            container=project+"-postgres-1"
        parameters={"host":"127.0.0.1","port":port,"user":"dpr_bootstrap","password":password,
            "dbname":"postgres","connect_timeout":3,"sslmode":"disable"}
        for _ in range(60):
            try:
                with psycopg.connect(**parameters,autocommit=True) as connection:
                    connection.execute("CREATE DATABASE protected_734")
                break
            except psycopg.OperationalError: time.sleep(0.25)
        else: raise RuntimeError("Isolated PG18 not ready")
        parameters["dbname"]="protected_734"
        profile=apply.load_profile(REPO/"policy/protection_profile.yaml")
        if native:
            # The production SQL builder and role-env handling run unchanged.
            # Substitute only the Docker exec transport with the same PG18 psql.
            def native_psql(command,**kwargs):
                command=[executable("psql"),"-X","-w","-q","-v","ON_ERROR_STOP=1","-h","127.0.0.1","-p",str(port),
                    "-U",command[command.index("-U")+1],"-d",command[command.index("-d")+1]]
                kwargs["env"]={**kwargs["env"],"PGPASSWORD":password,"PGSSLMODE":"disable"}
                return subprocess.run(command,**kwargs)
            with pytest.MonkeyPatch.context() as patch:
                patch.setattr(apply,"subprocess",SimpleNamespace(run=native_psql))
                apply.provision(container,"protected_734","dpr_bootstrap",role_passwords,profile)
        else:
            apply.provision(container,"protected_734","dpr_bootstrap",role_passwords,profile)
        def pg_command(program,database,user):
            tool_env={**environment,"PGPASSWORD":role_passwords.get(user,password),"PGSSLMODE":"disable"}
            if native: command=[executable(program),"-h","127.0.0.1","-p",str(port)]
            else: command=["docker","exec","-i","--env","PGPASSWORD","--env","PGSSLMODE",container,program]
            return command+["-U",user,"-d",database],tool_env
        yield {"params":parameters,"passwords":role_passwords,"transport":"native_pg18" if native else "docker_pg18","pg_command":pg_command}
    finally:
        if started:
            if native: run([executable("pg_ctl"),"-D",str(data),"-m","immediate","-w","stop"],silent=True)
            else: run(compose+["down","--volumes","--remove-orphans"],env=environment)


def test_analyst_denial_small_cells_upgrade_and_restore(analyst_lab):
    lab=analyst_lab; checks={}
    report={"schema_version":1,"passed":False,"scope":"fresh isolated PG18; invented rows only; no organizer data or benchmark hosts",
        "transport":lab["transport"],"tls_in_scope":False,"threshold":5,"fixture_group_sizes":[1,2,3,4,5,6],"checks":checks}
    def connect(role="dpr_bootstrap",database="protected_734"):
        return psycopg.connect(**{**lab["params"],"dbname":database,"user":role,
            "password":lab["passwords"].get(role,lab["params"]["password"])},autocommit=True)
    def denied(statement):
        with connect("analyst_user") as connection:
            try: connection.execute(statement)
            except psycopg.errors.InsufficientPrivilege as error: return error.sqlstate=="42501"
            return False
    dimensions=("jenis_kelamin","pekerjaan_terakhir","nama_kppn","nama_bank","age_band")
    wrapped="vault:v1:"+base64.b64encode(os.urandom(48)).decode()
    insert="""INSERT INTO public.anggota_protected
        (anggota_id,legacy_row_id,protection_version,dek_pii_wrapped,dek_fin_wrapped,
         jenis_kelamin,pekerjaan_terakhir,nama_kppn,nama_bank,age_band)
         VALUES(%s,%s,1,%s,%s,%s,%s,%s,%s,%s)"""
    def add(connection,number,labels):
        connection.execute(insert,(str(uuid4()),number,wrapped,wrapped,*labels))
    try:
        with connect() as admin:
            report["postgres_version"]=admin.execute("SELECT version()").fetchone()[0].split(",")[0]
            row=0
            for size in range(1,7):
                labels=(chr(64+size),f"Synthetic job {size}",f"Synthetic office {size}",f"Synthetic bank {size}",f"{size*10}-{size*10+9}")
                for _ in range(size): row+=1; add(admin,row,labels)
            for _ in range(4): row+=1; add(admin,row,(None,)*5)
            checks["fresh_provisioning_metadata"]=apply.inspect_schema(lab["params"],apply.load_profile(REPO/"policy/protection_profile.yaml"))["passed"]
        checks["base_select_denied_42501"]=denied("SELECT * FROM public.anggota_protected")
        checks["raw_view_select_denied_42501"]=denied("SELECT * FROM public.analyst_view")
        checks["raw_column_select_denied_42501"]=denied("SELECT jenis_kelamin FROM public.analyst_view")
        checks["account_select_denied_42501"]=denied("SELECT * FROM public.app_users")
        with connect("analyst_user") as reader:
            rows=reader.execute("SELECT dimension,value,anggota_count FROM public.analyst_summary").fetchall()
            checks["only_five_dimensions"]=set(row[0] for row in rows)==set(dimensions)
            checks["groups_1_to_4_labels_absent"]=len(rows)==10 and all(row[2] in {5,6} for row in rows)
            checks["null_group_4_absent"]=not any(row[1] is None for row in rows)
            expected={"jenis_kelamin":[("E",5),("F",6)],
                "pekerjaan_terakhir":[("Synthetic job 5",5),("Synthetic job 6",6)],
                "nama_kppn":[("Synthetic office 5",5),("Synthetic office 6",6)],
                "nama_bank":[("Synthetic bank 5",5),("Synthetic bank 6",6)],
                "age_band":[("50-59",5),("60-69",6)]}
            for dimension in dimensions:
                checks[dimension+":groups_5_and_6_exact"]=sorted((value,n) for d,value,n in rows if d==dimension)==expected[dimension]
            checks["legacy_age_function_suppressed"]=sorted(n for _,n in reader.execute("SELECT * FROM public.analyst_age_summary()"))==[5,6]
            checks["postfilter_cannot_reintroduce_small_labels"]=reader.execute("SELECT * FROM public.analyst_summary WHERE value='Synthetic job 1'").fetchall()==[]
        with connect() as admin:
            row+=1; add(admin,row,(None,)*5)
            admin.execute("ALTER ROLE migration_user NOLOGIN")
            admin.execute("SET ROLE schema_owner")
            admin.execute("CREATE TABLE public.service_a5_sentinel(id integer PRIMARY KEY)")
            admin.execute("INSERT INTO public.service_a5_sentinel VALUES(1)")
            admin.execute("GRANT SELECT ON public.service_a5_sentinel TO app_user")
            admin.execute("RESET ROLE")
            before=admin.execute("SELECT md5(string_agg(t::text,',' ORDER BY legacy_row_id)) FROM public.anggota_protected t").fetchone()[0]
            # Simulate an old deployment plus a stray column ACL, then upgrade it.
            admin.execute("GRANT SELECT ON public.analyst_view TO analyst_user")
            admin.execute("GRANT SELECT(jenis_kelamin) ON public.anggota_protected TO analyst_user")
            admin.execute("CREATE OR REPLACE FUNCTION public.analyst_age_summary() RETURNS TABLE(age_band varchar(10),anggota_count bigint) LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS 'SELECT age_band,count(*) FROM public.analyst_view GROUP BY age_band'")
            with admin.transaction(): checks["existing_install_upgrade"]=all(analyst.upgrade(admin).values())
            with admin.transaction(): checks["upgrade_idempotent"]=all(analyst.upgrade(admin).values())
            checks["member_rows_unchanged"]=before==admin.execute("SELECT md5(string_agg(t::text,',' ORDER BY legacy_row_id)) FROM public.anggota_protected t").fetchone()[0]
            checks["migration_stays_nologin"]=not admin.execute("SELECT rolcanlogin FROM pg_roles WHERE rolname='migration_user'").fetchone()[0]
            checks["service_grants_and_rows_preserved"]=admin.execute("SELECT has_table_privilege('app_user','public.service_a5_sentinel','SELECT') AND (SELECT count(*)=1 FROM public.service_a5_sentinel)").fetchone()[0]
            # Reject a PUBLIC read path atomically, rather than claim isolation.
            admin.execute("GRANT SELECT(id) ON public.service_a5_sentinel TO PUBLIC")
            with pytest.raises(psycopg.errors.RaiseException), admin.transaction(): analyst.upgrade(admin)
            admin.execute("REVOKE SELECT(id) ON public.service_a5_sentinel FROM PUBLIC")
            checks["public_column_bypass_rejected"]=True
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier("dpr_restore_"+"a"*32)))
            # Never target baseline/postgres with the upgrade, even inside this lab.
        with connect(database="postgres") as admin:
            with pytest.raises(psycopg.errors.RaiseException), admin.transaction(): analyst.upgrade(admin)
            checks["baseline_target_guard"]=True
        checks["stray_column_acl_removed"]=denied("SELECT jenis_kelamin FROM public.anggota_protected")
        checks["old_view_grant_removed"]=denied("SELECT * FROM public.analyst_view")
        with connect("analyst_user") as reader:
            rows=reader.execute("SELECT * FROM public.analyst_summary").fetchall()
            checks["null_group_5_released"]=sum(value is None and n==5 for _,value,n in rows)==5
            checks["all_released_counts_at_least_5"]=len(rows)==15 and all(n>=5 for _,_,n in rows)
            checks["old_function_upgrade_no_bypass"]=sorted(n for _,n in reader.execute("SELECT * FROM public.analyst_age_summary()"))==[5,5,6]
        # Actual PG18 custom-format dump/restore with former raw-view grants.
        # Dump bytes stay in memory, with no plaintext temporary archive.
        with connect() as admin:
            admin.execute("GRANT SELECT ON public.analyst_view TO analyst_user")
            admin.execute("CREATE OR REPLACE FUNCTION public.analyst_age_summary() RETURNS TABLE(age_band varchar(10),anggota_count bigint) LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS 'SELECT age_band,count(*) FROM public.analyst_view GROUP BY age_band'")
        command,environment=lab["pg_command"]("pg_dump","protected_734","backup_user")
        dumped=subprocess.run(command+["--format=custom","--enable-row-security"],env=environment,capture_output=True,timeout=60)
        assert dumped.returncode==0 and dumped.stdout.startswith(b"PGDMP"), "Synthetic in-memory dump failed"
        with connect() as admin:
            with admin.transaction(): analyst.upgrade(admin)
        command,environment=lab["pg_command"]("pg_restore","dpr_restore_"+"a"*32,"dpr_bootstrap")
        restored_process=subprocess.run(command+["--single-transaction","--exit-on-error"],input=dumped.stdout,env=environment,capture_output=True,timeout=60)
        assert restored_process.returncode==0, "Synthetic in-memory restore failed"
        with connect(database="dpr_restore_"+"a"*32) as restored:
            checks["old_archive_reproduces_raw_grant"]=restored.execute("SELECT has_table_privilege('analyst_user','public.analyst_view','SELECT')").fetchone()[0]
            restored.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier("dpr_restore_"+"a"*32)))
            with restored.transaction(): checks["old_restore_acl_hardened"]=all(analyst.upgrade(restored).values())
            checks["restored_security_acceptance"]=all(check_restored_security(restored).values())
            checks["restored_member_rows_unchanged"]=before==restored.execute("SELECT md5(string_agg(t::text,',' ORDER BY legacy_row_id)) FROM public.anggota_protected t").fetchone()[0]
        report["passed"]=all(checks.values())
        assert report["passed"], ", ".join(name for name,passed in checks.items() if not passed)
    finally:
        report["checked_at_utc"]=datetime.now(timezone.utc).isoformat()
        report["member_rows_in_fixture"]=26
        output=REPO/"evidence/access-control/analyst_suppression.json"
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
