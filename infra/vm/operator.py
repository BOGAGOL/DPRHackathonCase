"""Fresh-VM private materials and read-only verification. Never print secret values."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
from urllib.parse import quote, urlencode, urlsplit
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from dprcrypto import OpenBaoClient
from infra.openbao.api import BaoError, from_environment
from infra.openbao.init import configure, issue_tokens, save_response
from infra.postgres.development import read_source
from infra.postgres.enable_tls import ExistingPostgres
from infra.protected.apply import load_profile
from infra.protected.analyst import security_checks as analyst_security_checks
from infra.protected.credentials import ROLES, role_environment
from infra.security import REPO, external_directory, secure_directory, write_private
from migration.model import compare_batch


PASSWORD_NAMES = ("PGPASSWORD", *(role_environment(role) for role in ROLES))


def private_json(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Expected private regular file")
    if os.name != "nt" and (path.stat().st_mode & 0o077 or path.stat().st_uid != os.getuid()):
        raise ValueError("Expected owner-only private file")
    return json.loads(path.read_text(encoding="utf-8"))


def credentials(root):
    values = private_json(root/"database-credentials.json")
    if set(values) != set(PASSWORD_NAMES) or any(not isinstance(v,str) or not re.fullmatch(r"[A-Za-z0-9_-]{40,128}",v) for v in values.values()):
        raise ValueError("Unexpected credential material")
    return values


def save_environment(path, values):
    if path.is_symlink():
        raise ValueError("Refusing environment symlink")
    if any(not re.fullmatch(r"[A-Z][A-Z0-9_]*",name) or "\x00" in str(value) for name,value in values.items()):
        raise ValueError("Unexpected environment entry")
    temporary = path.with_name(path.name+"."+uuid4().hex+".tmp")
    content = "".join(name+"="+shlex.quote(str(value))+"\n" for name,value in values.items())
    try:
        write_private(temporary,content.encode("utf-8"))
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def endpoints(root):
    if os.environ.get("PGPORT","5433")!="5433": raise ValueError("The project port is 5433")
    return {"DPR_SECRETS_DIR":str(root),"PGHOST":os.environ.get("PGHOST","127.0.0.1"),"PGPORT":"5433",
        "PGSSLROOTCERT":str(root/"postgres/tls/ca.crt"),
        "OPENBAO_ADDR":os.environ.get("OPENBAO_ADDR","https://127.0.0.1:8200"),
        "OPENBAO_CACERT":str(root/"tls/ca.crt")}


def initialize_credentials(root, uid=None, gid=None):
    uid = uid if uid is not None else getattr(os,"getuid",lambda:1000)()
    gid = gid if gid is not None else getattr(os,"getgid",lambda:1000)()
    if type(uid) is not int or type(gid) is not int or not 1 <= uid <= 2147483647 or not 1 <= gid <= 2147483647:
        raise ValueError("Use the non-root VM operator UID/GID")
    project=os.environ.get("DPR_VM_PROJECT","dpr-demo")
    if not re.fullmatch(r"dpr-[a-z0-9][a-z0-9-]{0,45}",project): raise ValueError("Expected dedicated DPR project")
    compose_env=root/"compose.env"
    if compose_env.exists():
        if compose_env.is_symlink(): raise ValueError("Unexpected Compose environment")
        previous=dict(item.split("=",1) for item in shlex.split(compose_env.read_text()))
        if any(previous.get(name)!=value for name,value in {"DPR_VM_PROJECT":project,"DPR_VM_UID":str(uid),"DPR_VM_GID":str(gid)}.items()):
            raise ValueError("Existing runtime identity/project must not change")
    path=root/"database-credentials.json"; password_file=root/"postgres-password"
    if not path.exists():
        if password_file.exists(): raise ValueError("Incomplete material; refusing replacement")
        write_private(path,(json.dumps({name:secrets.token_urlsafe(36) for name in PASSWORD_NAMES})+"\n").encode())
    values=credentials(root)
    if password_file.is_symlink(): raise ValueError("Unexpected password file")
    if not password_file.exists(): write_private(password_file,(values["PGPASSWORD"]+"\n").encode())
    elif password_file.read_text().strip() != values["PGPASSWORD"]: raise ValueError("Password files disagree")
    environment={**endpoints(root),**values,"PGUSER":"postgres","DPR_VM_PROJECT":project,
        "DPR_POSTGRES_CONTAINER":project+"-postgres-1","DPR_VM_UID":str(uid),"DPR_VM_GID":str(gid)}
    save_environment(root/"operator.env",environment)
    save_environment(root/"compose.env",{name:environment[name] for name in ("DPR_SECRETS_DIR","DPR_VM_PROJECT","DPR_POSTGRES_CONTAINER","DPR_VM_UID","DPR_VM_GID")})
    return {"passed":True,"private_material_created_or_preserved":True,"credential_values_printed":False}


def database_parameters(root, database, role="postgres", readonly=False):
    env=endpoints(root); values=credentials(root)
    return {"host":env["PGHOST"],"port":5433,"dbname":database,"user":role,
        "password":values["PGPASSWORD" if role=="postgres" else role_environment(role)],
        "sslmode":"verify-full","sslrootcert":env["PGSSLROOTCERT"],"gssencmode":"disable","connect_timeout":5,
        "options":"-c default_transaction_read_only=on" if readonly else "-c log_statement=none -c log_min_error_statement=panic -c log_parameter_max_length_on_error=0 -c log_min_messages=panic"}


def token(root, policy):
    if policy not in {"svc-app","svc-migration"}: raise ValueError("Unexpected workload policy")
    files=list((root/"openbao/tokens").glob(policy+"-*.json"))
    if not files: raise ValueError("Workload token unavailable")
    latest=max(files,key=lambda path:(path.stat().st_mtime_ns,path.name))
    return private_json(latest)["auth"]["client_token"]


@contextmanager
def service_client(root):
    name="DPR_VM_SVC_APP_TOKEN"
    previous=os.environ.get(name)
    os.environ[name]=token(root,"svc-app")
    try:
        with OpenBaoClient(token_env=name) as client:
            client.require_policy("svc-app")
            yield client
    finally:
        if previous is None: os.environ.pop(name,None)
        else: os.environ[name]=previous


def bootstrap_bao(root, ttl, app_only=False):
    # Explicit operator command; no runtime action automatically loads root material.
    if type(ttl) is not int or not 60 <= ttl <= 14400: raise ValueError("Token TTL must be 60..14400 seconds")
    material=private_json(root/"openbao/init-material.json")
    api=from_environment()
    if app_only:
        destination=secure_directory(root/"openbao/tokens")/("svc-app-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-"+uuid4().hex[:8]+".json")
        save_response(destination,lambda:api.request("/auth/token/create-orphan",{
            "policies":["svc-app"],"no_default_policy":True,"renewable":False,
            "ttl":str(ttl)+"s","explicit_max_ttl":str(ttl)+"s","display_name":"dpr-svc-app"},token=material["root_token"]))
    else:
        configure(api,material["root_token"])
        issue_tokens(api,material["root_token"],root,ttl)
    return {"passed":True,"transit_configured":not app_only,"token_ttl_seconds":ttl,"unseal_automated":False,"app_only":app_only}


def workload_environment(root):
    values=credentials(root)
    environment={**endpoints(root),"DPR_SOURCE_USER":"scanner_user","DPR_SOURCE_PASSWORD":values["DPR_SCANNER_USER_PASSWORD"],
        "DPR_MIGRATION_USER_PASSWORD":values["DPR_MIGRATION_USER_PASSWORD"],
        "OPENBAO_MIGRATION_TOKEN":token(root,"svc-migration"),"OPENBAO_VALIDATION_TOKEN":token(root,"svc-app")}
    save_environment(root/"migration.env",environment)
    return {"passed":True,"migration_env_contains_admin_or_root_credentials":False}


def import_source(root, source_file):
    rows=read_source(source_file)
    target=ExistingPostgres(os.environ.get("DPR_POSTGRES_CONTAINER","dpr-demo-postgres-1"))
    if target.info.get("Config",{}).get("Labels",{}).get("dpr.scope") != "vm-demo":
        raise ValueError("Initial import requires the dedicated fresh-VM container")
    with psycopg.connect(**database_parameters(root,"postgres")) as connection:
        identity=connection.execute("SELECT system_identifier::text FROM pg_control_system()").fetchone()[0]
        if identity != target.query("SELECT system_identifier::text FROM pg_control_system();"):
            raise ValueError("Container and TLS connection differ")
        if connection.execute("SELECT to_regclass('public.anggota')").fetchone()[0] is not None:
            raise ValueError("Source exists; initial import refuses overwrite")
        schema=(REPO/"sql/baseline/01_schema.sql").read_text(encoding="utf-8-sig")
        # CREATE must fail if another initializer races us; never execute the baseline DROP.
        if schema.count("DROP TABLE IF EXISTS anggota;")!=1:
            raise ValueError("Unexpected baseline DDL; import refused")
        schema=schema.replace("DROP TABLE IF EXISTS anggota;","")
        if re.search(r"\bDROP\s+",schema,re.I): raise ValueError("Destructive baseline DDL refused")
        connection.execute(schema)
        columns=list(rows[0])
        query=sql.SQL("INSERT INTO public.anggota ({}) VALUES ({})").format(sql.SQL(",").join(map(sql.Identifier,columns)),sql.SQL(",").join(sql.Placeholder() for _ in columns))
        with connection.cursor() as cursor: cursor.executemany(query,[[row[name] for name in columns] for row in rows])
        actual=connection.execute("SELECT count(*),count(DISTINCT no_ktp),min(length(no_ktp)),max(length(no_ktp)),count(*) FILTER(WHERE status_kawin='K'),count(tanggal_pernikahan) FROM public.anggota").fetchone()
        if actual != (734,734,14,14,367,367): raise ValueError("Source aggregate validation failed")
        connection.execute("GRANT CONNECT ON DATABASE postgres TO scanner_user")
        connection.execute("GRANT USAGE ON SCHEMA public TO scanner_user")
        connection.execute("GRANT SELECT ON public.anggota TO scanner_user")
    return {"passed":True,"source_rows":734,"source_input_sha256":hashlib.sha256(source_file.read_bytes()).hexdigest(),"initial_import_only":True,"dataset_values_printed":False}


def retire_migration(root):
    with psycopg.connect(**database_parameters(root,"protected_734")) as connection:
        state=connection.execute("SELECT status,source_database,source_rows,migrated_rows FROM public.migration_jobs WHERE job_id=1").fetchone()
        count=connection.execute("SELECT count(*) FROM public.anggota_protected").fetchone()[0]
        if state != ("validated","postgres",734,734) or count != 734: raise ValueError("Complete validated migration required")
        connection.execute("ALTER ROLE migration_user NOLOGIN")
    return {"passed":True,"migration_role_nologin":True}


def handoff(root, origin):
    parsed=urlsplit(origin)
    if parsed.scheme!="https" or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ("","/") or parsed.query or parsed.fragment:
        raise ValueError("An HTTPS application origin is required")
    env=endpoints(root); values=credentials(root)
    with service_client(root):
        app_token=os.environ["DPR_VM_SVC_APP_TOKEN"]
    def url(role):
        password=values["PGPASSWORD" if role=="postgres" else role_environment(role)]
        return "postgresql+psycopg://"+role+":"+quote(password,safe="")+"@"+env["PGHOST"]+":5433/protected_734?"+urlencode({"sslmode":"verify-full","sslrootcert":env["PGSSLROOTCERT"]})
    app={"MODE":"protected","DATABASE_URL":url("app_user"),"AUTH_DATABASE_URL":url("app_user"),
        "ANALYST_DATABASE_URL":url("analyst_user"),"AUDITOR_DATABASE_URL":url("auditor_user"),
        "OPENBAO_ADDR":env["OPENBAO_ADDR"],"OPENBAO_CACERT":env["OPENBAO_CACERT"],"OPENBAO_TOKEN":app_token,
        "DPR_CRYPTO_FACTORY":"dprcrypto:public-v1","APP_ORIGIN":origin.rstrip("/"),"SESSION_TTL_SECONDS":"900",
        "TLS_CERT_FILE":str(root/"tls/server.crt"),"TLS_KEY_FILE":str(root/"tls/server.key"),
        "NODE_EXTRA_CA_CERTS":env["OPENBAO_CACERT"],"API_INTERNAL_URL":"https://127.0.0.1:8100"}
    with psycopg.connect(**database_parameters(root,"postgres",readonly=True)) as connection:
        principal=connection.execute("SELECT pengguna FROM public.anggota WHERE id=1").fetchone()[0]
    directory=secure_directory(root/"handoff")
    save_environment(directory/"app.env",app)
    save_environment(directory/"setup.env",{"APP_SETUP_DATABASE_URL":url("postgres"),"DPR_PRIVATE_DIR":str(root.parent),"DEMO_ASSIGNED_IDS":"1,2","DEMO_MEMBER_PRINCIPAL":principal})
    return {"passed":True,"target":"protected_734","runtime_root_or_admin_present":False,"private_handoff_written":True}


def verify(root):
    profile=load_profile(REPO/"policy/protection_profile.yaml")
    checks={}; rows_compared=0
    # Only svc-app and scanner_user are used for field validation.
    with service_client(root) as client, \
            psycopg.connect(**database_parameters(root,"postgres","scanner_user",True),row_factory=dict_row) as source, \
            psycopg.connect(**database_parameters(root,"protected_734","scanner_user",True),row_factory=dict_row) as target:
        original=source.execute("SELECT * FROM public.anggota ORDER BY id").fetchall()
        protected=target.execute("SELECT * FROM public.anggota_protected ORDER BY legacy_row_id").fetchall()
        checks["matching_source_target_734"]=len(original)==len(protected)==734
        if not checks["matching_source_target_734"]: raise ValueError("Expected complete 734-row target")
        for start in range(0,734,100):
            compare_batch(original[start:start+100],protected[start:start+100],profile,client)
            rows_compared+=len(original[start:start+100])
        checks["all_fields_nulls_age_band_and_bidx_match"]=True
    with psycopg.connect(**database_parameters(root,"protected_734","backup_user",True)) as connection:
        checks["postgres18_tls"]=connection.execute("SELECT current_setting('server_version_num')::int/10000=18 AND ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()").fetchone()[0]
        roles=connection.execute("SELECT rolname,rolcanlogin,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication FROM pg_roles WHERE rolname=ANY(%s)",(["schema_owner",*ROLES],)).fetchall()
        checks["roles_minimal"]=len(roles)==8 and all(not any(row[2:]) for row in roles)
        checks["owner_and_migration_nologin"]=all(not row[1] for row in roles if row[0] in {"schema_owner","migration_user"})
        checks["forced_rls"]=connection.execute("SELECT relrowsecurity AND relforcerowsecurity AND pg_get_userbyid(relowner)='schema_owner' FROM pg_class WHERE oid='public.anggota_protected'::regclass").fetchone()[0]
        checks["backup_cannot_update"]=not connection.execute("SELECT has_table_privilege(current_user,'public.anggota_protected','UPDATE')").fetchone()[0]
        checks["app_has_no_ddl"]=not connection.execute("SELECT has_schema_privilege('app_user','public','CREATE')").fetchone()[0]
        checks.update(analyst_security_checks(connection))
    for role in ("app_user","analyst_user","auditor_user"):
        with psycopg.connect(**database_parameters(root,"protected_734",role,True)) as connection:
            checks[role+":verified_tls"]=connection.execute("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()").fetchone()[0]
            if role=="app_user": checks["app_default_rls_denies"]=connection.execute("SELECT count(*) FROM public.anggota_protected").fetchone()[0]==0
            else:
                try: connection.execute("SELECT count(*) FROM public.anggota_protected")
                except psycopg.errors.InsufficientPrivilege: checks[role+":base_table_denied"]=True
                else: checks[role+":base_table_denied"]=False
    try:
        from_environment().request("/auth/token/lookup-self",token=token(root,"svc-migration"))
    except BaoError as error:
        checks["migration_identity_rejected"]=error.status==403
    else:
        checks["migration_identity_rejected"]=False
    return {"passed":all(checks.values()),"checks":checks,"source":"postgres","target":"protected_734","rows_compared":rows_compared,"scope":"Module A infrastructure/data acceptance; web and six-account acceptance separate"}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=("init-secrets","bootstrap-bao","refresh-app","workload-env","import-source","retire-migration","handoff","verify"))
    parser.add_argument("--source",type=Path)
    parser.add_argument("--ttl-seconds",type=int,default=14400)
    parser.add_argument("--uid",type=int); parser.add_argument("--gid",type=int)
    parser.add_argument("--app-origin",default="https://localhost:3443")
    parser.add_argument("--evidence-dir",type=Path,default=REPO/"evidence/deployment")
    args=parser.parse_args(argv)
    report={"schema_version":1,"command":args.command,"passed":False,"checked_at_utc":datetime.now(timezone.utc).isoformat()}
    try:
        root=secure_directory(external_directory(os.environ.get("DPR_SECRETS_DIR")))
        if args.command=="init-secrets": result=initialize_credentials(root,args.uid,args.gid)
        elif args.command=="bootstrap-bao": result=bootstrap_bao(root,args.ttl_seconds)
        elif args.command=="refresh-app": result=bootstrap_bao(root,args.ttl_seconds,app_only=True)
        elif args.command=="workload-env": result=workload_environment(root)
        elif args.command=="import-source":
            if args.source is None: raise ValueError("A private source file is required")
            result=import_source(root,args.source)
        elif args.command=="retire-migration": result=retire_migration(root)
        elif args.command=="handoff": result=handoff(root,args.app_origin)
        else: result=verify(root)
        report.update(result)
    except (Exception,KeyboardInterrupt):
        report["error"]="vm_operation_failed_details_withheld"
    args.evidence_dir.mkdir(parents=True,exist_ok=True)
    output=args.evidence_dir/("vm-"+args.command+".json")
    output.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"passed":report["passed"],"command":args.command,"report":str(output)}))
    return 0 if report["passed"] else 1
