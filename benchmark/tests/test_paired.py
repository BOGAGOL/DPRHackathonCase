import gzip
import json
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from benchmark import paired, runner, collect_metrics, db_time


def test_admin_is_separate_verified_identity_and_targets(monkeypatch):
    monkeypatch.setattr(paired,'monitoring_parameters',lambda:{'user':'postgres','sslmode':'verify-full'})
    assert paired.admin_parameters('protected_1m')['options'].endswith('=on')
    assert paired.admin_parameters('protected_1m',True)['options'].endswith('=off')
    with pytest.raises(ValueError):paired.admin_parameters('foreign')
    connection=MagicMock()
    monkeypatch.setattr(db_time,'monitoring_parameters',lambda:{'user':'postgres'})
    monkeypatch.setattr(db_time.psycopg,'connect',lambda **p:connection)
    monitor=object.__new__(db_time.DbTimeMonitor)
    monitor.reset()
    connection.__enter__.return_value.execute.assert_called_once_with('SELECT public.pg_stat_statements_reset()')


def test_service_guard_no_restart_no_unseal(monkeypatch):
    monkeypatch.setattr(paired,'running_containers',lambda:paired.CONTAINERS)
    monkeypatch.setattr(paired.shutil,'disk_usage',lambda p:SimpleNamespace(free=21*1024**3))
    api=MagicMock();api.request.return_value={'initialized':True,'sealed':False}
    monkeypatch.setattr(paired,'from_environment',lambda:api)
    paired.services()
    api.request.assert_called_once_with('/sys/seal-status')
    api.request.return_value['sealed']=True
    with pytest.raises(RuntimeError):paired.services()
    monkeypatch.setattr(paired,'running_containers',lambda:['pg-dpr'])
    with pytest.raises(RuntimeError):paired.services()


@pytest.mark.parametrize('ttl,minimum,accepted',[(14400,10800,True),(10800,10800,True),
    (10799,10800,False),(5400,5400,True),(5399,5400,False),(0,5400,False),
    ('14400',5400,False),(True,5400,False),(float('nan'),5400,False)])
def test_token_gate_never_reads_private_files_or_issues(monkeypatch,ttl,minimum,accepted):
    monkeypatch.setenv('OPENBAO_TOKEN','synthetic-workload-token')
    monkeypatch.delenv('DPR_SECRETS_DIR',raising=False)
    forbidden=MagicMock(side_effect=AssertionError('No private file access is authorized'))
    monkeypatch.setattr(paired.Path,'read_text',forbidden)
    monkeypatch.setattr(paired.Path,'open',forbidden)
    api=MagicMock();api.request.return_value={'data':{'policies':['svc-app'],'ttl':ttl}}
    monkeypatch.setattr(paired,'from_environment',lambda:api)
    if accepted:
        result=paired.ensure_token(minimum)
        assert result['ttl_seconds']==ttl and not result['new_4h_token_issued']
        assert result['automatic_issuance'] is False
    else:
        with pytest.raises(RuntimeError,match='benchmark_token_ttl_below_threshold'):
            paired.ensure_token(minimum)
    api.request.assert_called_once_with('/auth/token/lookup-self',token='synthetic-workload-token')
    forbidden.assert_not_called()
    assert paired.os.environ['OPENBAO_TOKEN']=='synthetic-workload-token'


@pytest.mark.parametrize('policies',[['root'],['svc-app','default'],['svc-migration'],[]])
def test_token_gate_rejects_any_extra_or_wrong_policy(monkeypatch,policies):
    monkeypatch.setenv('OPENBAO_TOKEN','synthetic-workload-token')
    api=MagicMock();api.request.return_value={'data':{'policies':policies,'ttl':14400}}
    monkeypatch.setattr(paired,'from_environment',lambda:api)
    with pytest.raises(RuntimeError,match='benchmark_token_policy_not_only_svc_app'):
        paired.ensure_token()
    assert api.request.call_count==1


def test_token_gate_missing_lookup_failure_and_bad_threshold_are_closed(monkeypatch):
    api=MagicMock();api.request.side_effect=ValueError('synthetic-private-error')
    monkeypatch.setattr(paired,'from_environment',lambda:api)
    monkeypatch.delenv('OPENBAO_TOKEN',raising=False)
    with pytest.raises(RuntimeError,match='benchmark_token_missing'):paired.ensure_token()
    api.request.assert_not_called()
    monkeypatch.setenv('OPENBAO_TOKEN','synthetic-workload-token')
    with pytest.raises(RuntimeError,match='^benchmark_token_lookup_failed$'):paired.ensure_token()
    for threshold in (0,-1,True,'10800'):
        with pytest.raises(ValueError,match='invalid_token_ttl_threshold'):paired.ensure_token(threshold)
    assert api.request.call_count==1


def test_integrity_covers_all_five_databases_and_ciphertext_hash(monkeypatch,tmp_path):
    monkeypatch.setattr(paired,'ROOT',tmp_path)
    d=tmp_path/'evidence/datasets';d.mkdir(parents=True)
    for name in ['baseline_100k','baseline_1m']:
        (d/(name+'.json')).write_text(json.dumps({'baseline_checksum_sha256':'digest','validation':{'source_checksum_sha256':'digest'}}))
    monkeypatch.setattr(paired,'checksum',lambda c:'digest')
    monkeypatch.setattr(paired,'admin_parameters',lambda db:{'dbname':db})
    def connection(**params):
        c=MagicMock();c.__enter__.return_value=c
        def execute(query,*args):
            q=str(query); row={'n':734 if params['dbname']=='postgres' else 1000000 if params['dbname'].endswith('1m') else 100000}
            if 'last_value' in q:row={'last_value':100000,'is_called':True}
            c.execute.return_value.fetchone.return_value=row
            return c.execute.return_value
        c.execute.side_effect=execute
        c.cursor.return_value.__enter__.return_value.copy.return_value.__enter__.return_value.__iter__.return_value=[b'invented-binary-row']
        return c
    monkeypatch.setattr(paired.psycopg,'connect',connection)
    result=paired.integrity()
    assert len(result)==5 and result['protected_1m']['ciphertext_rows_binary_sha256']
    assert paired.unchanged(result,result)
    import copy
    altered=copy.deepcopy(result);altered['protected_1m']['ciphertext_rows_binary_sha256']='tampered'
    assert not paired.unchanged(result,altered)


def test_guard_latches_ac_and_service_failure(monkeypatch):
    power=SimpleNamespace(collection_failure=None,samples=[{'ac_online':False}])
    g=paired.RunGuard(power);g.start();g.thread.join(timeout=2)
    assert g.finish()=='ac_interrupted' and g.stop.is_set()
    power.samples=[{'ac_online':True}]
    monkeypatch.setattr(paired,'services',MagicMock(side_effect=RuntimeError('invented')))
    g=paired.RunGuard(power);g.start();g.thread.join(timeout=2)
    assert g.finish()=='services_or_disk_gate_failed'


def test_raw_compression_is_roundtrip_checked(monkeypatch,tmp_path):
    content=b'timestamp,latency,error\n1,2,\n';(tmp_path/'resources.csv').write_bytes(content)
    result=paired.compress_run(tmp_path)
    assert not (tmp_path/'resources.csv').exists()
    assert gzip.open(tmp_path/'resources.csv.gz','rb').read()==content
    assert result[0]['uncompressed_bytes']==len(content)


def test_medians_keep_all_four_runs_and_show_old_and_absolute_failures():
    rows=[]
    for mode in ['B','P']:
        for n in range(4):
            x=1 if mode=='B' else 2
            rows.append({'mode':mode,'scenario':'read_by_nik','valid':True,'p50_ms':x,'p95_ms':x,
                         'p99_ms':x,'mean_ms':x,'throughput_rps':100,'error_rate':0,
                         'db_time':{'db_time_ms_per_request':.1},'client_non_db_mean_ms':x-.1,
                         'requests':100,'errors':0,'warmup_errors':0})
    a=paired.aggregate(rows); c=paired.comparison({'100k':a})['scales']['100k'][0]
    assert not c['P01_ratio_passed'] and c['P01_absolute_passed']
    assert not c['old_threshold_all_passed'] and c['absolute_with_P02_P03_passed']
    assert not c['all_current_targets_passed']
    with pytest.raises(ValueError):paired.aggregate(rows[:-1])
    a[0]['throughput_rps']=0
    assert paired.comparison({'100k':a})['scales']['100k'][0]['status']=='TIDAK DAPAT DINILAI'


def test_run_once_uses_authorized_parameters_and_safe_outputs(monkeypatch,tmp_path):
    now='2026-10-28T09:00:00+00:00'
    monkeypatch.setattr(paired,'utc_now',lambda:now)
    monkeypatch.setattr(paired,'services',lambda:None)
    monitor=MagicMock();monkeypatch.setattr(paired,'DbTimeMonitor',lambda *a:monitor)
    guard=MagicMock();guard.stop=threading.Event();guard.reason=None
    monkeypatch.setattr(paired,'RunGuard',lambda p:guard)
    result={'mean_ms':2,'db_time':{'db_time_ms_per_request':.2},'resources':{'samples':1,'failed_samples':0}}
    call=MagicMock(return_value=result);monkeypatch.setattr(paired,'one_run',call)
    monkeypatch.setattr(paired,'power_events',lambda *a:{'latest_event_at_or_before_start':{'ac_online':True},'events_in_window':[]})
    monkeypatch.setattr(paired,'admin_parameters',lambda *a:{})
    c=MagicMock();c.__enter__.return_value=c;c.execute.return_value.fetchone.return_value=(123,)
    monkeypatch.setattr(paired.psycopg,'connect',lambda **k:c)
    monkeypatch.setattr(paired,'compress_run',lambda p:[])
    power=MagicMock();power.samples=[{'timestamp_utc':now,'ac_online':True}]
    r=paired.run_once(object(),'P','protected_100k','read_profile',1,{},tmp_path,power)
    assert r['valid'] and r['client_non_db_mean_ms']==1.8
    assert call.call_args.args[4:7]==(8,60,10)
    assert call.call_args.kwargs['reset_statistics'] is True
    monitor.close.assert_called_once()


def test_paired_resource_parser_two_containers(monkeypatch):
    lines=[{'Name':'pg-dpr','CPUPerc':'120%','MemUsage':'1 GiB / 4 GiB'},
           {'Name':'dpr-infra-openbao-1','CPUPerc':'30%','MemUsage':'50 MiB / 4 GiB'}]
    monkeypatch.setattr(collect_metrics.subprocess,'run',lambda *a,**kw:SimpleNamespace(stdout='\n'.join(json.dumps(x) for x in lines)))
    s=collect_metrics.docker_sample(paired.CONTAINERS)
    assert s['db_cpu_percent_one_core']==120 and s['openbao_ram_bytes']==50*1024**2


def test_real_timing_runner_resets_and_redacts_errors(monkeypatch,tmp_path):
    class Adapter:
        def connect(self):return SimpleNamespace(close=lambda:None)
        def execute(self,*args):raise ValueError('invented-private-payload-must-not-leak')
    collector=MagicMock();collector.thread=None;collector.finish.return_value={'samples':1,'failed_samples':0}
    monitor=MagicMock();monitor.snapshot.return_value={'reset':'same','dealloc':0,'rows':{}}
    monkeypatch.setattr('benchmark.db_time.db_time_delta',lambda *a:{'db_time_ms_per_request':.1})
    manifest={'seed':42,'mixed_cycle':{'read_by_nik':20,'read_by_email':20,'read_profile':20,'list_page':10,'update_contact':15,'insert_member':15},'scenarios':['read_by_nik','read_by_email','read_profile','list_page','update_contact','insert_member','mixed']}
    r=runner.one_run(Adapter(),'read_by_nik',1,manifest,2,.02,.01,tmp_path/'raw',monitor,
                     reset_statistics=True,collector_factory=lambda p:collector)
    assert r['errors']>0 and r['error_types']=={'ValueError':r['errors']}
    monitor.reset.assert_called_once()
    assert 'invented-private-payload' not in ''.join(p.read_text() for p in (tmp_path/'raw').glob('*.csv'))


def test_execute_initial_gate_refuses_failed_or_existing_session(monkeypatch,tmp_path):
    monkeypatch.setattr(paired,'ROOT',tmp_path)
    out=tmp_path/'evidence/benchmark';out.mkdir(parents=True)
    (out/'bppb_preflight.json').write_text('{"passed": false}')
    with pytest.raises(ValueError):paired.execute()
    (out/'bppb_preflight.json').write_text('{"passed": true}')
    (out/'bppb_100k').mkdir();(out/'bppb_100k/session.json').write_text('{}')
    with pytest.raises(ValueError):paired.execute()


def test_full_block_repeated_after_power_failure_without_mixing(monkeypatch,tmp_path):
    monkeypatch.setattr(paired,'ROOT',tmp_path)
    monkeypatch.setattr(paired,'SCALES',{'100k':100000})
    out=tmp_path/'evidence/benchmark';out.mkdir(parents=True)
    (out/'bppb_preflight.json').write_text('{"passed":true}')
    (tmp_path/'benchmark').mkdir()
    names=['read_by_nik','read_by_email','read_profile','list_page','update_contact','insert_member','mixed']
    (tmp_path/'benchmark/workloads.yaml').write_text(json.dumps({'scenarios':names}))
    monkeypatch.setattr(paired,'services',lambda:None)
    monkeypatch.setattr(paired,'integrity',lambda:{})
    monkeypatch.setattr(paired,'ensure_token',lambda:{'ttl_seconds':14400})
    monkeypatch.setattr(paired,'load_keys',lambda *a:({},{}))
    monkeypatch.setattr(paired,'PlaintextAdapter',MagicMock())
    monkeypatch.setattr(paired,'ProtectedAdapter',MagicMock())
    monkeypatch.setattr(paired,'admin_parameters',lambda *a:{})
    c=MagicMock();c.__enter__.return_value=c
    monkeypatch.setattr(paired.psycopg,'connect',lambda **k:c)
    monkeypatch.setattr(paired,'prepare_scope',lambda *a:('invented-principal',1))
    cleanup=MagicMock();monkeypatch.setattr(paired,'remove_scope',cleanup)
    monkeypatch.setattr(paired.psutil,'sensors_battery',lambda:SimpleNamespace(power_plugged=True))
    monitors=[]
    class Power:
        def __init__(self,*args):self.number=len(monitors);monitors.append(self)
        def start(self):pass
        def finish(self):return {'qualified':self.number!=0}
    monkeypatch.setattr(paired,'ACMonitor',Power)
    def fake_run(adapter,mode,db,scenario,n,manifest,directory,power):
        return {'mode':mode,'database':db,'scenario':scenario,'run':n,'valid':True,'p50_ms':1,'p95_ms':2,
                'p99_ms':3,'mean_ms':1.5,'throughput_rps':10,'error_rate':0,'requests':10,'errors':0,
                'warmup_errors':0,'db_time':{'db_time_ms_per_request':.2},'client_non_db_mean_ms':1.3}
    monkeypatch.setattr(paired,'run_once',fake_run)
    result=paired.execute()
    assert result['status']=='COMPLETED'
    info=result['scales']['100k']
    assert len(info['rows'])==56 and len(info['attempts'])==3
    assert info['attempts'][0]['status']=='TERDAMPAK_BATERAI'
    assert all(not r['valid'] for r in info['attempts'][0]['runs'])
    assert all(r['attempt']==2 for r in info['rows'] if r['block']==1)
    assert (out/'bppb_100k/block_1/attempt_1/BLOCK_INVALID_BATTERY.json').exists()
    cleanup.assert_called_once()
