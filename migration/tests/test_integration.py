"""Real PG18 + OpenBao 2.5.5, both verified TLS; invented data, disposable volumes."""

from datetime import datetime, timezone
import json
import os
import secrets
import shutil
import subprocess
import threading
import time

import psycopg
import psutil
from psycopg import sql
from psycopg.rows import dict_row
import pytest

from dprcrypto import DecryptionError, OpenBaoClient, OpenBaoError
from infra.openbao.api import BaoAPI, BaoError
from infra.openbao.init import configure, initialize, issue_tokens, revoke_migration, unseal
from infra.postgres.enable_tls import ExistingPostgres, TLSUpdateError
from infra.postgres.make_cert import make_certificate
from infra.protected.apply import load_profile, provision
from infra.protected.credentials import ROLES
from infra.security import REPO, secure_directory
from infra.tls.make_ca import make_ca
from migration.model import MigrationError
from migration import cli
from migration.runner import LOCK, check_connections, execute, source_summary
from migration.tests.test_model import synthetic_row
from policy.build_profile import text_hashes


@pytest.mark.skipif(os.environ.get("DPR_MIGRATION_INTEGRATION")!="1",reason="Set DPR_MIGRATION_INTEGRATION=1 for disposable TLS migration test")
def test_real_migration_resume_all_fields_tamper_and_revocation(tmp_path,monkeypatch):
    scale_1m=int(os.environ.get("DPR_MIGRATION_1M_ROWS","1003"))
    free_at_start=shutil.disk_usage(REPO).free
    project="dpr-migrate-test-"+secrets.token_hex(5)
    root=secure_directory(tmp_path/"secrets")
    make_ca(root/"tls");make_certificate(root)
    password=secrets.token_urlsafe(36)
    env={**os.environ,"DPR_SECRETS_DIR":str(root),"DPR_POSTGRES_PORT":"0","DPR_OPENBAO_PORT":"0","DPR_POSTGRES_PASSWORD":password}
    command=["docker","compose","-p",project,"-f",str(REPO/"infra/compose.yaml"),"-f",str(REPO/"infra/tests/compose.postgres.yaml")]
    def compose(*args):
        result=subprocess.run(command+list(args),env=env,capture_output=True,text=True,timeout=180)
        if result.returncode:raise RuntimeError("Disposable migration compose failed; output withheld")
        return result.stdout.strip()
    report={"schema_version":1,"passed":False,"scope":"invented data only; disposable TLS PG18 + TLS OpenBao","checks":{},"validations":{}}
    observations={"host_free_at_start_bytes":free_at_start,"host_min_free_bytes":free_at_start,"sampled_peak_python_rss_bytes":0}
    stop=threading.Event()
    def sample_resources():
        process=psutil.Process()
        while not stop.wait(0.5):
            observations["host_min_free_bytes"]=min(observations["host_min_free_bytes"],shutil.disk_usage(REPO).free)
            observations["sampled_peak_python_rss_bytes"]=max(observations["sampled_peak_python_rss_bytes"],process.memory_info().rss)
    sampler=threading.Thread(target=sample_resources,daemon=True);sampler.start()
    original_call=OpenBaoClient._call
    def guarded_call(self,path,payload):
        if shutil.disk_usage(REPO).free<2*1024**3:
            raise RuntimeError("Host disk headroom below 2 GiB; disposable migration aborted")
        return original_call(self,path,payload)
    monkeypatch.setattr(OpenBaoClient,"_call",guarded_call)
    checks=report["checks"]
    try:
        if scale_1m>=1000000 and free_at_start<6*1024**3:
            raise RuntimeError("1M fixture requires at least 6 GiB of host disk headroom")
        compose("up","-d")
        container=project+"-postgres-1"
        pg_port=int(compose("port","postgres","5432").rsplit(":",1)[1])
        address="https://127.0.0.1:"+compose("port","openbao","8200").rsplit(":",1)[1]
        pg=ExistingPostgres(container,port=pg_port)
        for _ in range(80):
            try:pg.metadata();break
            except TLSUpdateError:time.sleep(0.5)
        else:raise RuntimeError("Disposable PG18 not ready")
        params={"host":"127.0.0.1","port":pg_port,"user":"dpr_bootstrap","password":password,"dbname":"postgres","autocommit":True}
        with psycopg.connect(**params) as admin:
            for database in ("baseline_100k","protected_734","protected_100k","baseline_1m","protected_1m"):
                admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        pg.apply(root)
        params.update(sslmode="verify-full",sslrootcert=str(root/"postgres/tls/ca.crt"),gssencmode="disable")
        profile=load_profile(REPO/"policy/protection_profile.yaml")
        profile_hashes=text_hashes(REPO/"policy/protection_profile.yaml")
        profile_hash=profile_hashes[-1]
        passwords={role:secrets.token_urlsafe(36) for role in ROLES}
        # Include quote/backslash punctuation to exercise psql literal escaping.
        passwords["migration_user"] += "'\"\\$"
        for target_name in ("protected_734","protected_100k","protected_1m"):
            provision(container,target_name,"dpr_bootstrap",passwords,profile)
        # Existing two-source installations must upgrade without erasing progress.
        with psycopg.connect(**{**params,"dbname":"protected_100k"}) as admin:
            admin.execute("ALTER TABLE public.migration_jobs DROP CONSTRAINT migration_jobs_source_database_check")
            admin.execute("ALTER TABLE public.migration_jobs ADD CONSTRAINT migration_jobs_source_database_check CHECK(source_database IN ('postgres','baseline_100k'))")
            admin.execute("INSERT INTO public.migration_jobs(job_id,source_database,source_identity,profile_sha256,source_sha256,source_rows,status) VALUES(1,'baseline_100k','synthetic-upgrade',%s,%s,0,'paused')",("0"*64,"0"*64))
        provision(container,"protected_100k","dpr_bootstrap",passwords,profile)
        with psycopg.connect(**{**params,"dbname":"protected_100k"}) as admin:
            checks["schema_upgrade_preserves_existing_checkpoint"]=admin.execute("SELECT source_identity,status FROM public.migration_jobs WHERE job_id=1").fetchone()==("synthetic-upgrade","paused")
            checks["schema_upgrade_accepts_1m_source"]= "baseline_1m" in admin.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='public.migration_jobs'::regclass AND conname='migration_jobs_source_database_check'").fetchone()[0]
            admin.execute("DELETE FROM public.migration_jobs WHERE job_id=1")
        api=BaoAPI(address,str(root/"tls/ca.crt"))
        for _ in range(80):
            try:state=api.request("/sys/seal-status");break
            except BaoError:time.sleep(0.5)
        else:raise RuntimeError("Disposable OpenBao not ready")
        initialize(api,root)
        material=json.loads((root/"openbao/init-material.json").read_text())
        for share in material["keys_base64"][:2]:unseal(api,share)
        configure(api,material["root_token"])
        issue_tokens(api,material["root_token"],root,14400)
        tokens={name:json.loads(next((root/"openbao/tokens").glob(name+"-*.json")).read_text())["auth"]["client_token"] for name in ("svc-app","svc-migration","svc-verify")}
        monkeypatch.setenv("OPENBAO_ADDR",address);monkeypatch.setenv("OPENBAO_CACERT",str(root/"tls/ca.crt"))
        monkeypatch.setenv("OPENBAO_MIGRATION_TOKEN",tokens["svc-migration"])
        monkeypatch.setenv("OPENBAO_VALIDATION_TOKEN",tokens["svc-app"])
        columns=["id",*profile["columns"]]
        for source_name,amount in (("postgres",734),("baseline_100k",int(os.environ.get("DPR_MIGRATION_SCALE_ROWS","1001"))),("baseline_1m",scale_1m)):
            with psycopg.connect(**{**params,"dbname":source_name}) as admin:
                definitions=[sql.SQL("{} {}").format(sql.Identifier(column),sql.SQL("bigint PRIMARY KEY" if column=="id" else "date" if column.startswith("tanggal_") else "smallint" if column.startswith("jumlah_") else "text")) for column in columns]
                admin.execute(sql.SQL("CREATE TABLE public.anggota({})").format(sql.SQL(",").join(definitions)))
                query=sql.SQL("COPY public.anggota({}) FROM STDIN").format(sql.SQL(",").join(map(sql.Identifier,columns)))
                with admin.cursor().copy(query) as copy:
                    for i in range(1,amount+1):
                        if i%10000==0 and shutil.disk_usage(REPO).free<2*1024**3:
                            raise RuntimeError("Insufficient host disk headroom for disposable source")
                        row=synthetic_row(i,profile)
                        copy.write_row([row[column] for column in columns])
        monkeypatch.setattr(cli,"REPO",tmp_path/"cli-reports")
        monkeypatch.setattr(cli,"runtime_parameters",lambda database,source:{**{key:value for key,value in params.items() if key!="autocommit"},"dbname":database,
            **({} if source else {"user":"migration_user","password":passwords["migration_user"]})})
        with OpenBaoClient(token_env="OPENBAO_MIGRATION_TOKEN") as migrator,OpenBaoClient(token_env="OPENBAO_VALIDATION_TOKEN") as validator:
            try:migrator.unwrap_batch("pii-kek",migrator.wrap_batch("pii-kek",[os.urandom(32)]));checks["migration_decrypt_denied"]=False
            except OpenBaoError:checks["migration_decrypt_denied"]=True
            for source_name,target_name in (("postgres","protected_734"),("baseline_100k","protected_100k"),("baseline_1m","protected_1m")):
                with psycopg.connect(**{**params,"dbname":source_name},row_factory=dict_row) as source, \
                     psycopg.connect(**{**params,"dbname":target_name,"user":"migration_user","password":passwords["migration_user"]},row_factory=dict_row) as target:
                    kwargs=dict(source_name=source_name,target_name=target_name,profile=profile,profile_hash=profile_hash,migration_client=migrator,validation_client=validator)
                    before=source_summary(source,profile)
                    checks[source_name+":tls"]=source.execute("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()").fetchone()["ssl"] and target.execute("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()").fetchone()["ssl"]
                    if source_name=="postgres":
                        with pytest.raises(MigrationError,match="unexpected_source_row_count"):
                            execute(source,target,**kwargs,expected_rows=735)
                        checks["unexpected_source_count_rejected_before_writes"]=target.execute("SELECT count(*) AS n FROM public.migration_jobs").fetchone()["n"]==0
                        with psycopg.connect(**{**params,"dbname":target_name,"user":"app_user","password":passwords["app_user"]}) as app:
                            with pytest.raises(psycopg.errors.InsufficientPrivilege):app.execute("SELECT * FROM public.migration_jobs")
                        checks["app_cannot_access_progress"]=True
                        paused=execute(source,target,**kwargs,batch_size=100,max_batches=1)
                        checks["first_batch_paused"]=paused["status"]=="paused" and paused["migrated_rows"]==100
                        saved=target.execute("SELECT anggota_id,nama_ct,dek_pii_wrapped FROM public.anggota_protected WHERE legacy_row_id=1").fetchone()
                        with pytest.raises(MigrationError,match="source_or_profile_changed"):
                            execute(source,target,**{**kwargs,"profile_hash":"0"*64})
                        checks["profile_change_rejected"]=True
                        with psycopg.connect(**{**params,"dbname":"postgres"}) as admin:
                            admin.execute("UPDATE public.anggota SET nama_bank=%s WHERE id=1",("Changed Synthetic Bank",))
                        with pytest.raises(MigrationError,match="source_or_profile_changed"):execute(source,target,**kwargs)
                        checks["source_change_rejected"]=True
                        with psycopg.connect(**{**params,"dbname":"postgres"}) as admin:
                            admin.execute("UPDATE public.anggota SET nama_bank=%s WHERE id=1",(synthetic_row(1,profile)["nama_bank"],))
                        with psycopg.connect(**{**params,"dbname":target_name},row_factory=dict_row) as admin:
                            with pytest.raises(MigrationError,match="unsafe_target_role"):check_connections(source,admin,source_name,target_name)
                            admin.execute("UPDATE public.migration_jobs SET last_legacy_id=99 WHERE job_id=1")
                        with pytest.raises(MigrationError,match="target_checkpoint_mismatch"):execute(source,target,**kwargs)
                        checks["checkpoint_drift_rejected"]=True
                        with psycopg.connect(**{**params,"dbname":target_name}) as admin:admin.execute("UPDATE public.migration_jobs SET last_legacy_id=100 WHERE job_id=1")
                        # Failure in the middle of executemany must roll back data + checkpoint.
                        with psycopg.connect(**{**params,"dbname":target_name}) as admin:
                            admin.execute("ALTER TABLE public.anggota_protected ADD CONSTRAINT fail_test_batch CHECK(legacy_row_id<>150)")
                        with pytest.raises(psycopg.errors.CheckViolation):execute(source,target,**kwargs,batch_size=100)
                        checks["failed_batch_atomic"]=target.execute("SELECT count(*) AS n FROM public.anggota_protected").fetchone()["n"]==100 and target.execute("SELECT migrated_rows FROM public.migration_jobs").fetchone()["migrated_rows"]==100
                        with psycopg.connect(**{**params,"dbname":target_name}) as admin:admin.execute("ALTER TABLE public.anggota_protected DROP CONSTRAINT fail_test_batch")
                        result=execute(source,target,**{**kwargs,"profile_hash":profile_hashes[0]},compatible_profile_hashes=profile_hashes,batch_size=150)
                        checks["line_endings_do_not_break_legacy_checkpoint"]=result["profile_sha256"]==profile_hash
                        checks["resume_preserves_existing_uuid_ct_wrapped"]=saved==target.execute("SELECT anggota_id,nama_ct,dek_pii_wrapped FROM public.anggota_protected WHERE legacy_row_id=1").fetchone()
                        fingerprints=target.execute("SELECT anggota_id,nama_ct,dek_pii_wrapped FROM public.anggota_protected ORDER BY legacy_row_id").fetchall()
                        execute(source,target,**kwargs)
                        checks["idempotent_no_reencryption"]=fingerprints==target.execute("SELECT anggota_id,nama_ct,dek_pii_wrapped FROM public.anggota_protected ORDER BY legacy_row_id").fetchall()
                        with psycopg.connect(**{**params,"dbname":target_name}) as admin:
                            original=admin.execute("SELECT nama_ct FROM public.anggota_protected WHERE legacy_row_id=1").fetchone()[0]
                            damaged=bytearray(original);damaged[-1]^=1
                            admin.execute("UPDATE public.anggota_protected SET nama_ct=%s WHERE legacy_row_id=1",(bytes(damaged),))
                        with pytest.raises(DecryptionError):execute(source,target,**kwargs,validate_only=True)
                        checks["stored_tamper_rejected"]=True
                        checks["failed_validation_not_marked_valid"]=target.execute("SELECT status FROM public.migration_jobs").fetchone()["status"]!="validated"
                        with psycopg.connect(**{**params,"dbname":target_name}) as admin:admin.execute("UPDATE public.anggota_protected SET nama_ct=%s WHERE legacy_row_id=1",(original,))
                        result=execute(source,target,**kwargs,validate_only=True)
                        with psycopg.connect(**{**params,"dbname":target_name},row_factory=dict_row) as competing:
                            competing.execute("SELECT pg_advisory_lock(%s)",(LOCK,))
                            with pytest.raises(MigrationError,match="migration_already_running"):execute(source,target,**kwargs)
                        checks["concurrent_run_rejected"]=True
                    elif source_name=="baseline_1m":
                        # Exercise the real 1M CLI, including an explicit non-default count in quick tests.
                        monkeypatch.setattr("sys.argv",["migration","run","--source",source_name,"--target",target_name,
                            "--profile",str(REPO/"policy/protection_profile.yaml"),"--expected-rows",str(scale_1m),"--keep-migration-token"])
                        cli.main()
                        result=json.loads((tmp_path/"cli-reports/evidence/migration/validation-protected_1m.json").read_text())
                        checks["1m_cli_expected_rows"]=result["expected_rows"]==scale_1m
                    else:result=execute(source,target,**kwargs,batch_size=1000)
                    checks[source_name+":all_fields_validated"]=result["passed"] and result["rows_compared"]==before["rows"]
                    checks[source_name+":source_unchanged"]=source_summary(source,profile)==before
                    report["validations"][target_name]=result
            monkeypatch.setattr("sys.argv",["migration","run","--source","postgres","--target","protected_734","--profile",str(REPO/"policy/protection_profile.yaml")])
            cli.main()
            cli_report=json.loads((tmp_path/"cli-reports/evidence/migration/validation.json").read_text())
            checks["cli_validation_json_and_default_revocation"]=cli_report["passed"] and cli_report["migration_token_revoked"]
            try:migrator.wrap_batch("pii-kek",[os.urandom(32)]);checks["revoked_migration_token_denied"]=False
            except OpenBaoError:checks["revoked_migration_token_denied"]=True
        report["passed"]=all(checks.values())
        if not report["passed"]:pytest.fail("Migration integration failed checks: "+", ".join(name for name,passed in checks.items() if not passed),pytrace=False)
    finally:
        stop.set();sampler.join(timeout=2)
        report["resource_observations"]=observations
        report["checked_at_utc"]=datetime.now(timezone.utc).isoformat()
        path=REPO/"evidence/migration/integration.json";path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
        if os.environ.get("DPR_MIGRATION_SCALE_ROWS")=="100000":
            path.with_name("integration-100k.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
        if scale_1m==1000000:
            path.with_name("integration-1m.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
        compose("down","--volumes","--remove-orphans")
