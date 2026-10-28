"""Disposable native PG18/OpenBao TLS lab when Docker Desktop is unavailable."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time
from types import SimpleNamespace

import psycopg
from psycopg import sql
import pytest

from dprcrypto import OpenBaoClient
from infra.openbao.api import BaoAPI, BaoError
from infra.openbao.init import initialize, unseal, configure, issue_tokens
from infra.postgres.make_cert import make_certificate
from infra.protected import apply
from infra.protected.credentials import ROLES
from infra.security import REPO, secure_directory, write_private
from infra.tls.make_ca import make_ca
from migration.model import protect_batch, target_columns
from scripts.backup import runner
from scripts.backup.drills import synthetic_member
from scripts.backup.postgres import Tools
from scripts.backup.settings import artifact_store


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1",0))
        return listener.getsockname()[1]


@contextmanager
def laboratory(folder):
    """Only random ports and a new outside-repo cluster; never existing pg-dpr."""
    pg_bin=Path(os.environ["DPR_NATIVE_PG_BIN"]).resolve()
    bao_bin=Path(os.environ["DPR_NATIVE_BAO_BIN"]).resolve()
    def executable(name): return str(pg_bin/(name+(".exe" if os.name=="nt" else "")))
    def run(command,*,silent=False,**kwargs):
        output={"stdout":subprocess.DEVNULL,"stderr":subprocess.DEVNULL} if silent else {"capture_output":True}
        result=subprocess.run(command,**output,**kwargs,timeout=180)
        if result.returncode: raise RuntimeError("Native acceptance command failed; details withheld")
        return result
    if b" 18." not in run([executable("postgres"),"--version"]).stdout:
        raise ValueError("PostgreSQL 18 required")
    if b"v2.5.5" not in run([str(bao_bin),"version"]).stdout:
        raise ValueError("Pinned OpenBao 2.5.5 required")
    root=secure_directory(folder/"secrets"); make_ca(root/"tls"); make_certificate(root);make_ca(root/"wrong-ca")
    data=root/"pgdata"; pg_started=False; bao_process=None
    password=secrets.token_urlsafe(36)
    pg_port,bao_port=free_port(),free_port()
    while bao_port==pg_port: bao_port=free_port()
    env={**os.environ,"PGPASSWORD":password,"PGSSLMODE":"verify-full",
        "PGSSLROOTCERT":str(root/"postgres/tls/ca.crt"),"PGHOST":"127.0.0.1","PGPORT":str(pg_port)}
    try:
        password_file=root/"init-password"; write_private(password_file,(password+"\n").encode())
        try:
            run([executable("initdb"),"-D",str(data),"-U","dpr_bootstrap","--encoding=UTF8","--locale=C",
                "--auth-host=scram-sha-256","--auth-local=scram-sha-256","--pwfile="+str(password_file)])
        finally: password_file.unlink(missing_ok=True)
        cert=(root/"postgres/tls/server.crt").as_posix().replace("'","''")
        key=(root/"postgres/tls/server.key").as_posix().replace("'","''")
        with (data/"postgresql.conf").open("a",encoding="utf-8") as configuration:
            configuration.write(f"\nlisten_addresses='127.0.0.1'\nport={pg_port}\nssl=on\nssl_cert_file='{cert}'\nssl_key_file='{key}'\nssl_min_protocol_version='TLSv1.2'\nlog_statement='none'\nlog_min_error_statement='panic'\nlog_parameter_max_length=0\nlog_parameter_max_length_on_error=0\n")
        (data/"pg_hba.conf").write_text("hostssl all all 127.0.0.1/32 scram-sha-256\nhostnossl all all 127.0.0.1/32 reject\nhostssl all all ::1/128 scram-sha-256\nhostnossl all all ::1/128 reject\n",encoding="utf-8")
        pg_started=True
        run([executable("pg_ctl"),"-D",str(data),"-l",str(root/"postgres.log"),"-w","start"],silent=True)
        params={"host":"127.0.0.1","port":pg_port,"user":"dpr_bootstrap","password":password,
            "dbname":"postgres","sslmode":"verify-full","sslrootcert":env["PGSSLROOTCERT"],"gssencmode":"disable","connect_timeout":5}
        with psycopg.connect(**params,autocommit=True) as admin:
            for name in ("baseline_100k","protected_734","protected_100k","baseline_1m","protected_1m"):
                admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        passwords={role:secrets.token_urlsafe(36) for role in ROLES}
        def psql_transport(command,**kwargs):
            native=[executable("psql"),"-X","-w","-q","-v","ON_ERROR_STOP=1","-U",command[command.index("-U")+1],"-d",command[command.index("-d")+1]]
            kwargs["env"]={**kwargs["env"],**{name:value for name,value in env.items() if name.startswith("PG")}}
            return subprocess.run(native,**kwargs)
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(apply,"subprocess",SimpleNamespace(run=psql_transport))
            profile=apply.load_profile(REPO/"policy/protection_profile.yaml")
            apply.provision("native-acceptance","protected_734","dpr_bootstrap",passwords,profile)
        bao_address=f"https://127.0.0.1:{bao_port}"
        configuration={"disable_mlock":True,"ui":False,"api_addr":bao_address,
            "storage":{"file":{"path":str(root/"bao-storage")}},
            "listener":{"tcp":{"address":f"127.0.0.1:{bao_port}","tls_cert_file":str(root/"tls/server.crt"),
                "tls_key_file":str(root/"tls/server.key"),"tls_min_version":"tls12"}}}
        config=root/"bao.json"; write_private(config,json.dumps(configuration).encode())
        flags={"creationflags":subprocess.CREATE_NO_WINDOW} if os.name=="nt" else {}
        bao_process=subprocess.Popen([str(bao_bin),"server","-config="+str(config)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**flags)
        api=BaoAPI(bao_address,str(root/"tls/ca.crt"))
        for _ in range(100):
            if bao_process.poll() is not None: raise RuntimeError("Native OpenBao startup failed; output withheld")
            try: api.request("/sys/seal-status");break
            except BaoError: time.sleep(.1)
        else: raise RuntimeError("Native OpenBao startup timeout")
        initialize(api,root)
        material=json.loads((root/"openbao/init-material.json").read_text())
        for share in material["keys_base64"][:2]:unseal(api,share)
        configure(api,material["root_token"]);issue_tokens(api,material["root_token"],root,3600)
        token=json.loads(next((root/"openbao/tokens").glob("svc-app-*.json")).read_text())["auth"]["client_token"]
        with pytest.MonkeyPatch.context() as patch:
            for name,value in {"OPENBAO_ADDR":bao_address,"OPENBAO_CACERT":str(root/"tls/ca.crt"),"OPENBAO_VALIDATION_TOKEN":token}.items():patch.setenv(name,value)
            with OpenBaoClient(token_env="OPENBAO_VALIDATION_TOKEN") as client:
                rows=[synthetic_member(profile,n) for n in range(1,18)]
                for n,row in enumerate(rows):row["pekerjaan_terakhir"]="Singleton A5 acceptance" if n==0 else "Released A5 acceptance"
                protected=protect_batch(rows,profile,client)
            columns=target_columns(profile)
            with psycopg.connect(**{**params,"dbname":"protected_734"}) as admin:
                statement=sql.SQL("INSERT INTO public.anggota_protected ({}) VALUES ({})").format(sql.SQL(",").join(map(sql.Identifier,columns)),sql.SQL(",").join(sql.Placeholder() for _ in columns))
                with admin.cursor() as cursor:cursor.executemany(statement,[[row[name] for name in columns] for row in protected])
            class NativeTools(Tools):
                def __init__(self,container,parameters):
                    super().__init__(container,parameters)
                    self.environment.update(PGPORT=str(parameters["port"]),PGHOST=parameters["host"],PGSSLROOTCERT=parameters["sslrootcert"])
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def command(self,program,arguments):
                    if program not in {"pg_dump","pg_restore","psql"}:raise ValueError("Invalid native tool")
                    return [executable(program),"--no-password",*arguments]
            patch.setattr(runner,"Tools",NativeTools)
            keys=(os.urandom(32),os.urandom(32)); store=artifact_store(str(root/"archives"))
            yield {"params":params,"backup_params":{**params,"dbname":"protected_734","user":"backup_user","password":passwords["backup_user"]},
                "container":"native-acceptance","keys":keys,"store":store,"profile":profile,"passwords":passwords,"root":root,
                "transport":"native_pg18_openbao_tls","small_label":"Singleton A5 acceptance"}
    finally:
        if bao_process and bao_process.poll() is None:
            bao_process.terminate()
            try:bao_process.wait(timeout=15)
            except subprocess.TimeoutExpired:bao_process.kill();bao_process.wait(timeout=5)
        if pg_started:run([executable("pg_ctl"),"-D",str(data),"-m","immediate","-w","stop"],silent=True)
