"""Real k6 and verified TLS against invented local data; never pg-dpr/OpenBao."""
import json
import os
from pathlib import Path
import secrets
import ssl
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from benchmark.api import runner as r
from infra.tls.make_ca import make_ca


@pytest.mark.skipif(os.name!='nt' or not r.K6.is_file(),reason='Windows + installed k6 required for isolated TLS script integration')
def test_real_k6_setup_load_summary_and_no_values_in_raw(tmp_path):
    directory=tmp_path/'cert';make_ca(directory)
    state={'logins':0,'gets':0};lock=threading.Lock()
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def log_message(self,*args):pass
        def respond(self,status,header=None):
            self.send_response(status)
            if header:self.send_header('Set-Cookie',header)
            self.send_header('Content-Length','2');self.end_headers();self.wfile.write(b'{}')
        def do_GET(self):
            if self.path=='/auth/csrf':return self.respond(200,'dpr_csrf=synthetic-csrf; Path=/; Secure')
            with lock:state['gets']+=1;n=state['gets']
            self.respond(500 if n%11==0 else 200)
        def do_POST(self):
            self.rfile.read(int(self.headers.get('content-length','0')))
            with lock:state['logins']+=1
            self.send_response(200)
            self.send_header('Set-Cookie','dpr_session=synthetic-session; Path=/; Secure; HttpOnly')
            self.send_header('Set-Cookie','dpr_csrf=synthetic-post-login; Path=/; Secure')
            self.send_header('Content-Length','2');self.end_headers();self.wfile.write(b'{}')
    server=ThreadingHTTPServer(('127.0.0.1',8100),Handler)
    ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(directory/'server.crt',directory/'server.key')
    # Do not let a cancelled client's TLS handshake block the accept/shutdown loop.
    server.socket=ctx.wrap_socket(server.socket,server_side=True,do_handshake_on_connect=False)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    secret=secrets.token_urlsafe(24)
    keys=tmp_path/'keys.json';keys.write_text(json.dumps({'profiles':[{'id':1,'no_ktp':'invented-lookup-value','email':'invented@fixture.invalid'}],'pages':[1]}))
    account=tmp_path/'account.json';account.write_text(json.dumps([{'role':'privileged_officer','username':'invented-fixture','password':secret}]))
    raw=tmp_path/'raw.json'
    env={**os.environ,'API_KEYS_FILE':str(keys),'API_ACCOUNT_FILE':str(account),'API_ENDPOINT':'api_search_nik',
         'API_WARMUP_SECONDS':'0','API_FIXTURE_CA':str(directory/'ca.crt'),'K6_NO_USAGE_REPORT':'true'}
    certificate_script="$c=[System.Security.Cryptography.X509Certificates.X509Certificate2]::new($env:API_FIXTURE_CA); $s=[System.Security.Cryptography.X509Certificates.X509Store]::new('Root','CurrentUser'); $s.Open('ReadWrite'); "
    source=(r.ROOT/'benchmark/api/load.js').read_text(encoding='utf-8')
    assert source.count('60 + warmupMs / 1000')==1
    # Exercise the same functions for two seconds on invented fixture data only.
    # Production duration remains 60 seconds and is also checked by k6 inspect.
    script=tmp_path/'fixture.js';script.write_text(source.replace('60 + warmupMs / 1000','2 + warmupMs / 1000'),encoding='utf-8')
    try:
        subprocess.run(['powershell.exe','-NoProfile','-Command',certificate_script+'$s.Add($c);$s.Close()'],env=env,check=True,capture_output=True)
        run=subprocess.run([str(r.K6),'run','--quiet','--include-system-env-vars','--log-output=none','--out','json='+str(raw),str(script)],
                           env=env,capture_output=True,timeout=30)
        assert run.returncode==0, 'k6 fixture failed; no private output printed'
        result=r.parse_raw(raw)
        assert state['logins']==8 and result['requests']>8 and result['errors']>0
        assert '500' in result['http_status_counts'] and '200' in result['http_status_counts']
        contents=raw.read_bytes()
        assert secret.encode() not in contents and b'invented-lookup-value' not in contents
        assert b'synthetic-session' not in contents and b'"url"' not in contents
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
        subprocess.run(['powershell.exe','-NoProfile','-Command',certificate_script+'$s.Remove($c);$s.Close()'],env=env,check=True,capture_output=True)
