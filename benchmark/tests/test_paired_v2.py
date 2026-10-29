import copy
import ctypes
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from benchmark import paired, paired_v2 as v2


def test_measured_snapshot_is_accepted_and_later_edits_are_rejected(monkeypatch,tmp_path):
    # The completed v2 session is pinned to 8a11ff7. Main may legitimately advance
    # (e.g. A5 policy), so exercise the strict historical gate on its own snapshot.
    session=json.loads((v2.OUT/'bppb_v2_session.json').read_text())
    paths=session['variant_metadata']['production_file_sha256']
    original_root=v2.ROOT
    original_check_output=v2.subprocess.check_output
    sources={p:original_check_output(['git','show',v2.REQUESTED+':'+p],cwd=original_root) for p in paths}
    for path,content in sources.items():
        local_path = 'evidence/benchmark/protocol-20261026.txt' if path == 'docs/targets.md' else path
        target=tmp_path/local_path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
    def frozen_show(args,**kwargs):
        assert args[:2]==['git','show'] and args[2].startswith(v2.REQUESTED+':')
        return sources[args[2].split(':',1)[1]]
    monkeypatch.setattr(v2,'ROOT',tmp_path)
    monkeypatch.setattr(v2.subprocess,'check_output',frozen_show)
    hashes = v2.production_manifest()
    assert 'benchmark/adapters/protected.py' in hashes
    assert 'toolkit/dprcrypto/https_pool.py' in hashes
    assert all(len(h) == 64 for h in hashes.values())
    assert set(hashes)==set(paths)
    profile=tmp_path/'policy/protection_profile.yaml'
    profile.write_bytes(profile.read_bytes()+b'\n# Later policy revision must not pass the old gate.\n')
    with pytest.raises(RuntimeError,match='production_differs_from_requested_commit'):
        v2.production_manifest()


def test_power_gate_requires_ac_best_performance_and_no_sleep(monkeypatch):
    ac = [True]
    monkeypatch.setattr(v2, 'ACMonitor', lambda *a: SimpleNamespace(sample=lambda: {'timestamp_utc':'2026-10-28T13:00:00+00:00','ac_online':ac[0]}))
    monkeypatch.setattr(v2, 'power_events', lambda *a: {'latest_event_at_or_before_start':{'ac_online':True}})
    class Function:
        def __call__(self, target):
            ctypes.memmove(target, UUID('ded574b5-45a0-4f42-8737-46345c09c238').bytes_le, 16)
            return 0
    monkeypatch.setattr(v2.ctypes, 'WinDLL', lambda name: SimpleNamespace(PowerGetEffectiveOverlayScheme=Function()))
    monkeypatch.setattr(v2.subprocess, 'check_output', lambda *a, **k: 'Current AC Power Setting Index: 0x00000000')
    assert v2.power_snapshot()['passed']
    ac[0] = False
    assert not v2.power_snapshot()['passed']
    ac[0] = True
    monkeypatch.setattr(v2.subprocess, 'check_output', lambda *a, **k: 'Current AC Power Setting Index: 0x00000001')
    assert not v2.power_snapshot()['passed']


def test_membership_matches_ignores_only_operational_control_counts():
    before={'baseline_100k':{'rows':1,'checksum_sha256':'a','sequence':[1,True]},
            'protected_100k':{'rows':1,'ciphertext_rows_binary_sha256':'b','control_counts':{'audit_log':2}}}
    after=copy.deepcopy(before); after['protected_100k']['control_counts']['audit_log']=3
    assert v2.members_match(before,after)
    after['protected_100k']['ciphertext_rows_binary_sha256']='tampered'
    assert not v2.members_match(before,after)


def test_failed_gate_stops_before_network_and_writes_evidence(monkeypatch,tmp_path):
    monkeypatch.setattr(v2,'OUT',tmp_path)
    monkeypatch.setattr(v2,'git',lambda *a:'wrong-branch')
    forbidden=MagicMock(side_effect=AssertionError('Network must not run'))
    monkeypatch.setattr(v2,'power_snapshot',forbidden)
    result=v2.preflight()
    assert not result['passed'] and not result['gates']['branch']['passed']
    assert (tmp_path/'bppb_v2_preflight.json').exists()
    forbidden.assert_not_called()


def test_sealed_service_reason_is_saved_without_any_database_connection(monkeypatch,tmp_path):
    original_root = v2.ROOT
    monkeypatch.setattr(v2,'OUT',tmp_path)
    monkeypatch.setattr(v2,'git',lambda *a:v2.BRANCH if a[0]=='branch' else 'synthetic-commit-time')
    monkeypatch.setattr(v2,'production_manifest',lambda:{})
    monkeypatch.setenv('DPR_OPENBAO_HTTP_TRANSPORT','https_pool')
    monkeypatch.setenv('DPR_BENCH_DEK_CACHE_TTL','0')
    monkeypatch.setattr(v2.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0))
    target=(original_root/'evidence/benchmark/protocol-20261026.txt').read_bytes()
    monkeypatch.setattr(v2.subprocess,'check_output',lambda *a,**k:target)
    monkeypatch.setattr(v2,'power_snapshot',lambda:{'passed':True})
    monkeypatch.setattr(v2.paired,'services',MagicMock(side_effect=RuntimeError('openbao_unavailable_or_sealed')))
    connection=MagicMock(side_effect=AssertionError('Database must not be reached'))
    monkeypatch.setattr(v2.psycopg,'connect',connection)
    report=v2.preflight()
    assert not report['passed']
    assert report['gates']['services']=={'passed':False,'reason':'openbao_unavailable_or_sealed'}
    connection.assert_not_called()


def test_version_report_uses_plain_from_each_session_and_shows_failures(monkeypatch,tmp_path):
    monkeypatch.setattr(v2,'OUT',tmp_path)
    before={'p50_ms':1.,'p95_ms':2.,'throughput_rps':100.,'error_rate':0.,'db_time_ms_per_request':.1}
    after=dict(before,p95_ms=6.,throughput_rps=10.)
    row=dict(paired.compare_metrics(before,after,'read_by_nik'),before=before,after=after)
    for name in ('bppb_compare.json','bppb_v2_compare.json'):
        (tmp_path/name).write_text(json.dumps({'scales':{scale:[row] for scale in paired.SCALES}}))
    (tmp_path/'bppb_v2_session.json').write_text(json.dumps({'status':'COMPLETED','datasets_unchanged':True,
        'scales':{'100k':{'attempts':[],'rows':[]}}}))
    text=v2.versions_summary().read_text()
    assert 'naive_v1' in text and 'v2' in text and 'plain' in text
    assert 'GAGAL | LULUS | GAGAL | LULUS' in text


def test_initial_token_failure_stops_before_database_connections(monkeypatch,tmp_path):
    original_root=v2.ROOT
    monkeypatch.setattr(v2,'OUT',tmp_path)
    monkeypatch.setattr(v2,'git',lambda *a:v2.BRANCH if a[0]=='branch' else 'synthetic-time')
    monkeypatch.setattr(v2,'production_manifest',lambda:{})
    monkeypatch.setenv('DPR_OPENBAO_HTTP_TRANSPORT','https_pool')
    monkeypatch.setenv('DPR_BENCH_DEK_CACHE_TTL','0')
    monkeypatch.setattr(v2.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0))
    monkeypatch.setattr(v2.subprocess,'check_output',lambda *a,**k:(original_root/'evidence/benchmark/protocol-20261026.txt').read_bytes())
    monkeypatch.setattr(v2,'power_snapshot',lambda:{'passed':True})
    monkeypatch.setattr(v2.paired,'services',lambda:None)
    token=MagicMock(side_effect=RuntimeError('benchmark_token_ttl_below_threshold'))
    monkeypatch.setattr(v2.paired,'ensure_token',token)
    connection=MagicMock(side_effect=AssertionError('Database must not be reached'))
    monkeypatch.setattr(v2.psycopg,'connect',connection)
    report=v2.preflight()
    token.assert_called_once_with(minimum_ttl_seconds=10800)
    assert not report['passed'] and report['gates']['benchmark_token']['automatic_issuance'] is False
    connection.assert_not_called()


def test_publication_is_explicit_branch_and_own_paths(monkeypatch,tmp_path):
    monkeypatch.setattr(v2,'ROOT',tmp_path); monkeypatch.setattr(v2,'OUT',tmp_path/'evidence/benchmark')
    v2.OUT.mkdir(parents=True); (tmp_path/'benchmark').mkdir()
    (tmp_path/'evidence/benchmark').mkdir(parents=True,exist_ok=True); (tmp_path/'evidence/benchmark/run-notes.md').write_text('preserve existing')
    (v2.OUT/'bppb_v2_session.json').write_text('{}')
    monkeypatch.setattr(v2,'git',lambda *a:v2.BRANCH if a[0]=='branch' else 'synthetic-git-result')
    calls=[]
    monkeypatch.setattr(v2.subprocess,'run',lambda args,**kwargs:calls.append(args))
    receipt=v2.publish({'status':'COMPLETED'})
    assert receipt['status']=='PUSHED'
    commit=next(c for c in calls if 'commit' in c)
    assert '--only' in commit and 'main' not in commit
    assert calls[-1][-1]=='HEAD:refs/heads/perf/keyservice-latency'


def test_detached_driver_rejects_stale_or_failed_gate_and_duplicate(monkeypatch,tmp_path):
    monkeypatch.setattr(v2,'ROOT',tmp_path); monkeypatch.setattr(v2,'OUT',tmp_path/'evidence/benchmark')
    v2.OUT.mkdir(parents=True); (tmp_path/'benchmark').mkdir();(tmp_path/'evidence/benchmark').mkdir(parents=True,exist_ok=True); (tmp_path/'evidence/benchmark/run-notes.md').write_text('preserve')
    (v2.OUT/'bppb_v2_preflight.json').write_text('{"passed":false}')
    monkeypatch.setattr(v2,'publish',lambda s:{'status':'PUSHED'})
    assert v2.run()['status']=='STOPPED'
    assert 'preserve' in (tmp_path/'evidence/benchmark/run-notes.md').read_text()
    with pytest.raises(FileExistsError):v2.run()


def test_detached_worker_revalidates_three_hour_token_before_workload(monkeypatch,tmp_path):
    monkeypatch.setattr(v2,'ROOT',tmp_path);monkeypatch.setattr(v2,'OUT',tmp_path/'evidence/benchmark')
    v2.OUT.mkdir(parents=True);(tmp_path/'benchmark').mkdir();(tmp_path/'evidence/benchmark').mkdir(parents=True,exist_ok=True); (tmp_path/'evidence/benchmark/run-notes.md').write_text('preserve')
    (v2.OUT/'bppb_v2_preflight.json').write_text(json.dumps({'passed':True,'completed_at_utc':paired.utc_now()}))
    monkeypatch.setattr(v2,'production_manifest',lambda:{})
    monkeypatch.setenv('DPR_OPENBAO_HTTP_TRANSPORT','https_pool');monkeypatch.setenv('DPR_BENCH_DEK_CACHE_TTL','0')
    monkeypatch.setattr(v2,'power_snapshot',lambda:{'passed':True})
    token=MagicMock(side_effect=RuntimeError('benchmark_token_ttl_below_threshold'))
    monkeypatch.setattr(v2.paired,'ensure_token',token)
    workload=MagicMock(side_effect=AssertionError('Workload must not run'))
    monkeypatch.setattr(v2.paired,'execute',workload)
    monkeypatch.setattr(v2,'publish',lambda s:{'status':'PUSHED'})
    assert v2.run()['status']=='STOPPED'
    token.assert_called_once_with(minimum_ttl_seconds=10800)
    workload.assert_not_called()


def test_cli_and_prefix_guard(monkeypatch):
    monkeypatch.setattr(v2,'preflight',lambda:{'passed':True})
    monkeypatch.setattr(v2.os.sys,'argv',['v2','preflight'])
    with pytest.raises(SystemExit) as result:v2.main()
    assert result.value.code==0
    with pytest.raises(ValueError):paired.execute(prefix='../unsafe')
