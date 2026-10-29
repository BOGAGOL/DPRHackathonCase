import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest

from benchmark.api import client as c,runner as r


def test_http_login_and_all_get_routes_never_log_private_values():
    paths=[]
    def handler(request):
        paths.append((request.method,request.url.path))
        if request.url.path=='/auth/csrf':return httpx.Response(200,headers={'set-cookie':'dpr_csrf=synthetic; Path=/; Secure'})
        if request.url.path=='/auth/login':
            assert request.headers['x-csrf-token']=='synthetic'
        return httpx.Response(200,json={'items':[]})
    session=httpx.Client(base_url=c.BASE,transport=httpx.MockTransport(handler))
    c.login(session,{'username':'fixture','password':os.urandom(20).hex()})
    key={'id':42,'no_ktp':'invented','email':'invented@fixture.invalid'}
    for endpoint in c.ENDPOINTS:assert c.request(session,endpoint,key,1).status_code==200
    with pytest.raises(ValueError):c.request(session,'PATCH',key,1)
    assert paths[2:]==[('GET','/anggota'),('GET','/anggota/42'),('GET','/anggota/search'),('GET','/anggota/search')]
    assert c.mismatched_fields({'items':[{'nama':'a'}]},{'items':[{'nama':'b'}]})==['items.0.nama']
    assert c.mismatched_fields({'a':[]},{'b':[]})==['a','b']
    assert c.mismatched_fields([],['a'])==['length']
    assert c.mismatched_fields(None,None)==[]


def test_environment_separates_admin_and_workload_credentials(monkeypatch):
    monkeypatch.setenv('PROTECTED_DATABASE_URL','postgresql://app_user:synthetic@127.0.0.1:5433/protected_100k?sslmode=verify-full&sslrootcert=C%3A%2Ffixture%2Fca.crt')
    monkeypatch.setenv('BENCH_MONITOR_DATABASE_URL','postgresql://postgres:synthetic-admin@127.0.0.1:5433/baseline_100k?sslmode=verify-full&sslrootcert=C%3A%2Ffixture%2Fca.crt')
    for key in ('OPENBAO_ADDR','OPENBAO_CACERT','OPENBAO_TOKEN'):monkeypatch.setenv(key,'synthetic-'+key)
    plain=r.application_env('plain');protected=r.application_env('protected')
    assert 'OPENBAO_TOKEN' not in plain and 'BENCH_MONITOR_DATABASE_URL' not in protected
    assert 'app_user' in plain['DATABASE_URL'] and 'verify-full' in plain['DATABASE_URL']
    assert 'postgres:' in r.service_url('baseline_100k',True)
    assert protected['DPR_BENCH_DEK_CACHE_TTL']=='0'


def test_raw_parser_only_measurement_points_and_all_errors(tmp_path):
    path=tmp_path/'raw.json'
    points=[{'metric':'http_req_duration','type':'Point','data':{}},
            *[{'metric':'api_latency_ms','type':'Point','data':{'value':v,'time':t,'tags':{'ok':ok,'status':status}}}
              for v,t,ok,status in [(2,'2026-10-29T00:00:00Z','1','200'),(10,'2026-10-29T00:01:00Z','0','500')]]]
    path.write_text('\n'.join(json.dumps(p) for p in points))
    report=r.parse_raw(path)
    assert report['requests']==2 and report['errors']==1 and report['http_status_counts']=={'200':1,'500':1}
    assert report['p95_ms']>9


def test_comparison_requires_two_runs_and_records_operator_design_change():
    rows=[]
    for endpoint in c.ENDPOINTS:
        for mode in ('plain','protected'):
            for _ in range(2):rows.append({'endpoint':endpoint,'mode':mode,'valid':True,
                'p50_ms':1,'p95_ms':2 if mode=='plain' else 6,'p99_ms':7,'mean_ms':3,'throughput_rps':100,'error_rate':0})
    comparison=r.compare(rows);record=comparison['scenarios'][0]
    assert not record['P01_ratio_passed'] and record['P01_absolute_passed'] and record['P02_passed'] and record['P03_passed']
    assert comparison['design_change']['total_runs']==16
    assert comparison['design_change']['blocks']==1
    assert comparison['design_change']['targets_changed'] is False
    assert 'three-run minimum' in comparison['design_change']['limitation']
    with pytest.raises(RuntimeError):r.compare(rows[:-1])
    with pytest.raises(RuntimeError):r.compare(rows+rows)


def test_supervisor_recovers_only_unfinished_worker_not_failed_recovery(monkeypatch,tmp_path):
    p=tmp_path/'state.json';monkeypatch.setattr(r,'JOURNAL',p)
    monkeypatch.setattr(r.subprocess,'run',lambda *a,**k:None)
    recovery=MagicMock();monkeypatch.setattr(r,'recover',recovery)
    p.write_text('{"status":"swapped"}');r.supervise();recovery.assert_called_once()
    p.write_text('{"status":"restore_failed"}')
    with pytest.raises(RuntimeError):r.supervise()
    assert recovery.call_count==1
    p.write_text('{"status":"restored"}');r.supervise();assert recovery.call_count==1


def test_worker_setup_failure_always_restores_before_publication(monkeypatch,tmp_path):
    monkeypatch.setattr(r,'RAW',tmp_path/'raw');monkeypatch.setattr(r,'OUT',tmp_path/'out');r.OUT.mkdir()
    monkeypatch.setattr(r,'JOURNAL',tmp_path/'journal.json')
    monkeypatch.setenv('DPR_PRIVATE_DIR',str(tmp_path))
    monkeypatch.setattr(r,'preflight',lambda:{'passed':True,'before':{},'code_commit':'fixture','production_sha256':{}})
    monkeypatch.setattr(r,'secure_directory',lambda p:p)
    store=MagicMock();monkeypatch.setattr(r,'PGStore',lambda:store)
    swap=MagicMock();swap.state={'status':'swapped'};monkeypatch.setattr(r,'Swap',lambda *a:swap)
    app=MagicMock();monkeypatch.setattr(r,'App',lambda *a:app)
    monkeypatch.setattr(r.subprocess,'check_output',lambda *a,**k:'k6 fixture')
    monkeypatch.setattr(r,'prepare',MagicMock(side_effect=RuntimeError('fixture-failure')))
    check=MagicMock();monkeypatch.setattr(r,'verify_restored',check)
    publication=MagicMock();monkeypatch.setattr(r,'publish',publication)
    result=r.run()
    assert result['status']=='STOPPED'
    swap.restore.assert_called_once();check.assert_called_once_with(swap,{})
    store.close.assert_called_once();publication.assert_called_once()


def test_services_are_read_only_and_fail_on_seal_or_extra_container(monkeypatch):
    monkeypatch.setattr(r,'running_containers',lambda:r.paired.CONTAINERS)
    monkeypatch.setattr(r.shutil,'disk_usage',lambda p:SimpleNamespace(free=20*1024**3))
    api=MagicMock();api.request.return_value={'initialized':True,'sealed':False}
    monkeypatch.setattr(r,'from_environment',lambda:api);r.services()
    api.request.assert_called_once_with('/sys/seal-status')
    api.request.return_value['sealed']=True
    with pytest.raises(RuntimeError):r.services()


def test_guarded_setup_records_only_command_identity_and_status(monkeypatch,tmp_path):
    monkeypatch.setattr(r,'OUT',tmp_path)
    monkeypatch.setattr(r.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0))
    r.guarded_command(['python','app/scripts/schema.py'],{'MODE':'plain'})
    assert json.loads((tmp_path/'setup_progress.json').read_text())['status']=='PASS'
    monkeypatch.setattr(r.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=1))
    with pytest.raises(RuntimeError):r.guarded_command(['python','app/scripts/provision.py'],{'MODE':'protected'})
    assert json.loads((tmp_path/'setup_progress.json').read_text())['status']=='FAIL'


def test_restore_verification_checks_every_control_sequence_and_real_nossl_identities(monkeypatch,tmp_path):
    before={db:{'rows':n,'checksum_sha256':'same','sequence':[1,True],'all_control_tables':{},'all_sequences':[]}
            for db,n in [('baseline_100k',100000),('baseline_1m',1000000)]}
    monkeypatch.setattr(r,'OUT',tmp_path)
    monkeypatch.setattr(r,'official_snapshot',lambda:before)
    monkeypatch.setattr(r.paired_v2,'members_match',lambda *a:True)
    monkeypatch.setenv('BENCH_DATABASE_URL','postgresql://bench_user@127.0.0.1:5433/baseline_100k')
    monkeypatch.setenv('SCANNER_DATABASE_URL','postgresql://scanner_user@127.0.0.1:5433/baseline_100k')
    params=[]
    def connect(**p):
        params.append(p);conn=MagicMock();conn.__enter__.return_value=conn
        conn.execute.return_value.fetchone.side_effect=[(before[p['dbname']]['rows'],),(False,)]
        return conn
    monkeypatch.setattr(r.psycopg,'connect',connect)
    swap=MagicMock();swap.state={}
    r.verify_restored(swap,before)
    swap.save.assert_called_once_with('restored')
    assert len(params)==4 and {p['user'] for p in params}=={'scanner_user','bench_user'}
    assert all(p['sslmode']=='disable' and p['options'].endswith('=on') for p in params)


def test_app_stop_clears_journal_without_signalling_foreign_process(monkeypatch):
    swap=MagicMock();swap.state={'status':'swapped','app':{'pid':42}}
    app=r.App(swap,Path('.'));proc=MagicMock();proc.poll.return_value=None;app.proc=proc
    stop=MagicMock();monkeypatch.setattr(r,'stop_owned_app',stop)
    app.stop();stop.assert_called_once_with({'pid':42});proc.wait.assert_called_once_with(timeout=10)
    assert swap.state['app'] is None and app.proc is None


def test_parity_body_mismatch_is_reported_as_field_names_only(monkeypatch,tmp_path):
    monkeypatch.setattr(r,'OUT',tmp_path)
    accounts={m:tmp_path/(m+'.json') for m in ('plain','protected')}
    for p in accounts.values():p.write_text(json.dumps([{'role':'privileged_officer','username':'fixture','password':'not-active'}]))
    app=MagicMock();current=['plain']
    app.start.side_effect=lambda mode:current.__setitem__(0,mode)
    session=MagicMock();session.__enter__.return_value=session
    monkeypatch.setattr(r,'client',lambda *a:session);monkeypatch.setattr(r,'login',lambda *a:None)
    monkeypatch.setattr(r,'request',lambda *a:SimpleNamespace(status_code=200,json=lambda:{'nama':'invented-a' if current[0]=='plain' else 'invented-b'}))
    with pytest.raises(RuntimeError,match='parity_mismatch'):r.parity(app,{'profiles':[{'id':1}],'pages':[1]},accounts)
    text=(tmp_path/'parity.json').read_text()
    assert 'nama' in text and 'invented-a' not in text and 'invented-b' not in text


def test_preflight_failure_is_evidence_without_mutation(monkeypatch,tmp_path):
    monkeypatch.setattr(r,'OUT',tmp_path)
    monkeypatch.setattr(r.subprocess,'check_output',lambda *a,**k:'wrong-branch')
    forbidden=MagicMock(side_effect=AssertionError('No services after branch failure'))
    monkeypatch.setattr(r,'services',forbidden)
    assert not r.preflight()['passed'];forbidden.assert_not_called()


def test_windows_server_children_stop_before_parent_and_reused_pid_is_refused(monkeypatch):
    parent=MagicMock();parent.pid=10;parent.create_time.return_value=1;parent.cmdline.return_value=['python','app/scripts/serve.py']
    child=MagicMock();child.pid=20;child.create_time.return_value=2;child.cmdline.return_value=['python','app/scripts/serve.py']
    parent.children.return_value=[child]
    monkeypatch.setattr(r.psutil,'pid_exists',lambda pid:True)
    monkeypatch.setattr(r.psutil,'Process',lambda pid:parent if pid==10 else child)
    calls=[];parent.terminate.side_effect=lambda:calls.append(10);child.terminate.side_effect=lambda:calls.append(20)
    monkeypatch.setattr(r.psutil,'wait_procs',lambda p,timeout:(p,[]))
    monkeypatch.setattr(r.psutil,'net_connections',lambda **k:[])
    r.stop_owned_app({'pid':10,'created':1,'children':[{'pid':20,'created':2}]})
    assert calls==[20,10]
    with pytest.raises(RuntimeError):r.stop_owned_app({'pid':10,'created':999})


def test_copy_connection_grants_never_apply_to_official_oid(monkeypatch):
    swap=MagicMock();swap.state={'status':'swapped','copies':{'baseline_100k':111},'originals':{'baseline_100k':{'oid':11}}}
    swap.store.entries.return_value={'baseline_100k':{'oid':111}}
    monkeypatch.setattr(r.paired,'admin_parameters',lambda db,writable:{'dbname':db})
    conn=MagicMock();conn.__enter__.return_value=conn;conn.execute.return_value.fetchone.return_value=(111,)
    connect=MagicMock(return_value=conn);monkeypatch.setattr(r.psycopg,'connect',connect)
    r.grant_copy_prerequisites(swap,'baseline_100k')
    assert conn.execute.call_count==3
    swap.state['copies']['baseline_100k']=11
    with pytest.raises(RuntimeError,match='not_owned_copy'):r.grant_copy_prerequisites(swap,'baseline_100k')
    assert connect.call_count==1


def test_resources_use_only_measurement_window_and_retain_failures():
    rows=[{'timestamp_utc':f'2026-10-29T00:00:0{i}Z','ok':i!=2,'app_rss_bytes':v}
          for i,v in enumerate([9000,10,20,30,9999])]
    report=r.summarize_resources(rows,'2026-10-29T00:00:01+00:00','2026-10-29T00:00:03+00:00')
    assert report=={'samples':3,'failed_samples':1,'app_rss_bytes_median':20,'app_rss_bytes_peak':30}
    assert r.summarize_resources(rows)['app_rss_bytes_peak']==9999
    assert r.summarize_resources([],None,None)=={'samples':0,'failed_samples':0}
