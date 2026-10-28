"""Start owned HTTPS services for a real Chrome acceptance probe after restore."""
import base64
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from infra.security import REPO

# Root pytest also has a legacy package named app; load the reviewed B helper by
# its exact source path rather than resolving that unrelated package.
_spec=importlib.util.spec_from_file_location("dpr_acceptance_b_probe",REPO/"app/scripts/integration_probe.py")
_probe=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_probe)
free_loopback_port=_probe.free_loopback_port
stop_owned_process=_probe.stop_owned_process
wait_https=_probe.wait_https


def environments(settings,root,api_port,web_port):
    """Runtime receives only its three DB roles and svc-app; no admin/root env."""
    keep={"PATH","SystemRoot","SYSTEMROOT","WINDIR","COMSPEC","PATHEXT","USERPROFILE","HOME","LOCALAPPDATA","APPDATA","TEMP","TMP",
        "ProgramFiles","ProgramFiles(x86)","PROGRAMFILES","PROGRAMFILES(X86)","ProgramW6432"}
    base={name:value for name,value in os.environ.items() if name in keep}
    origin=f"https://localhost:{web_port}"
    tls={"TLS_CERT_FILE":str(root/"tls/server.crt"),"TLS_KEY_FILE":str(root/"tls/server.key")}
    api={**base,**tls,"MODE":"protected","DATABASE_URL":settings.database_url,
        "AUTH_DATABASE_URL":settings.auth_database_url or settings.database_url,
        "ANALYST_DATABASE_URL":settings.analyst_database_url,"AUDITOR_DATABASE_URL":settings.auditor_database_url,
        "DPR_RESTORED_DATABASE":settings.restored_database,"DPR_ALLOW_DISPOSABLE_DATABASE":"1","APP_ORIGIN":origin,
        "API_PORT":str(api_port),"SESSION_TTL_SECONDS":"900","OPENBAO_ADDR":settings.openbao_addr,
        "OPENBAO_CACERT":settings.openbao_cacert,"OPENBAO_TOKEN":os.environ["OPENBAO_VALIDATION_TOKEN"],"DPR_CRYPTO_FACTORY":"dprcrypto:public-v1"}
    web={**base,**tls,"APP_ORIGIN":origin,"WEB_PORT":str(web_port),"WEB_HOST":"127.0.0.1",
        "API_INTERNAL_URL":f"https://127.0.0.1:{api_port}","NODE_EXTRA_CA_CERTS":str(root/"tls/ca.crt"),
        "NODE_ENV":"production","NEXT_TELEMETRY_DISABLED":"1"}
    return api,web


def exercise(settings,accounts,root,*,small_label=None):
    """Use actual Next -> HTTPS API -> restored PG18 -> TLS OpenBao, without mocks."""
    node=shutil.which("node")
    if not node or not (REPO/"app/web/.next/BUILD_ID").exists():raise RuntimeError("Build app/web before browser acceptance")
    api_port,web_port=free_loopback_port(),free_loopback_port()
    while web_port==api_port:web_port=free_loopback_port()
    api_env,web_env=environments(settings,root,api_port,web_port)
    flags={"creationflags":subprocess.CREATE_NO_WINDOW} if os.name=="nt" else {}
    api=web=browser=None
    try:
        api=subprocess.Popen([sys.executable,str(REPO/"app/scripts/serve.py")],cwd=REPO,env=api_env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**flags)
        if not wait_https(f"https://127.0.0.1:{api_port}/health/ready",root/"tls/ca.crt",api):raise RuntimeError("Restored HTTPS API not ready")
        web=subprocess.Popen([node,"server.mjs"],cwd=REPO/"app/web",env=web_env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**flags)
        if not wait_https(web_env["APP_ORIGIN"]+"/login",root/"tls/ca.crt",web):raise RuntimeError("HTTPS web not ready")
        certificate=x509.load_pem_x509_certificate((root/"tls/server.crt").read_bytes())
        public_key=certificate.public_key().public_bytes(Encoding.DER,PublicFormat.SubjectPublicKeyInfo)
        pin=base64.b64encode(hashlib.sha256(public_key).digest()).decode()
        payload={"baseURL":web_env["APP_ORIGIN"],"accounts":accounts,"spki":pin,"otherRecordId":"2","smallLabel":small_label}
        browser=subprocess.Popen([node,str(REPO/"infra/acceptance/browser.mjs")],cwd=REPO,env=web_env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,**flags)
        stdout,_=browser.communicate(json.dumps(payload),timeout=240)
        result=json.loads(stdout)
        if not isinstance(result.get("checks"),dict) or not all(isinstance(value,bool) for value in result["checks"].values()):raise RuntimeError("Invalid sanitized browser evidence")
        result["api_tls_verified"]=True;result["web_tls_verified"]=True
        result["certificate_trust"]="verified private CA for service clients; exact ephemeral SPKI pin for local Chrome only"
        return result
    finally:
        for process in (browser,web,api):stop_owned_process(process)
