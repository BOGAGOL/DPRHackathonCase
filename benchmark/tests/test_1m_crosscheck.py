import json
import secrets
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import quote

import pytest

from benchmark import common, runner
from benchmark import backup_restore as backup
from benchmark import pgbench_crosscheck as pg
from benchmark.adapters import plaintext
from benchmark.stats import summarize
from benchmark.tests.test_sessions_cli_backup import MANIFEST


def test_disk_boundary_and_dataset_paths(monkeypatch,tmp_path):
    monkeypatch.setattr(common,'ROOT',tmp_path)
    assert common.session_paths('baseline_1m') == (tmp_path/'results/bench/before_1m',tmp_path/'evidence/benchmark/baseline_1m')
    assert common.session_paths('baseline_100k') == (common.RAW,common.EVIDENCE)
    with pytest.raises(ValueError): common.session_paths('protected_1m')
    monkeypatch.setattr(common.shutil,'disk_usage',lambda p:SimpleNamespace(free=10_000_000_000))
    assert common.require_disk_space(tmp_path)==10_000_000_000
    monkeypatch.setattr(common.shutil,'disk_usage',lambda p:SimpleNamespace(free=9_999_999_999))
    with pytest.raises(ValueError): common.require_disk_space(tmp_path)


def test_1m_parameters_and_corpus_isolation(monkeypatch,tmp_path,source):
    monkeypatch.setenv('BENCH_DATABASE_URL','postgresql://bench_user:'+quote(secrets.token_urlsafe(24))+'@127.0.0.1:5433/baseline_100k')
    monkeypatch.setenv('DATAGEN_DATABASE_URL','postgresql://postgres:'+quote(secrets.token_urlsafe(24))+'@127.0.0.1:5433/postgres')
    assert common.parameters('baseline_1m')['dbname']=='baseline_1m'
    assert common.parameters('baseline_1m',admin=True)['dbname']=='baseline_1m'
    with pytest.raises(ValueError): common.parameters('protected_1m',admin=True)
    monkeypatch.setattr(plaintext,'private_directory',lambda:tmp_path)
    payload={'database':'baseline_1m','seed':42,'concurrency':8,'profiles':source,'pages':[],'insert_templates':source[:8]}
    (tmp_path/'baseline_1m_keys_v1.json').write_text(json.dumps(payload,default=str))
    result,info=plaintext.load_keys({'seed':42},8,'baseline_1m')
    assert result['database']=='baseline_1m' and info['profile_count']==len(source)
    assert not (tmp_path/'baseline_100k_keys_v1.json').exists()
    with pytest.raises(ValueError): plaintext.load_keys({'seed':42},8,'../postgres')


def test_all_1m_runs_route_to_new_session_and_validate_whole_dataset(monkeypatch,tmp_path,source):
    monkeypatch.setattr(common,'ROOT',tmp_path);monkeypatch.setattr(runner,'ROOT',tmp_path)
    monkeypatch.setattr(common,'require_disk_space',lambda:20_000_000_000)
    (tmp_path/'benchmark').mkdir()
    (tmp_path/'benchmark/workloads.yaml').write_text(json.dumps(MANIFEST))
    (tmp_path/'evidence/datasets').mkdir(parents=True)
    (tmp_path/'evidence/datasets/baseline_1m.json').write_text(json.dumps({'baseline_checksum_sha256':'digest'}))
    original=tmp_path/'evidence/benchmark/baseline/summary.json'
    original.parent.mkdir(parents=True);original.write_text('original 100k evidence')
    saved={'rows':1000000,'checksum_sha256':'digest','sequence':{'last_value':1000000,'is_called':True},'storage':{}}
    seen=[]
    monkeypatch.setattr(runner,'state',lambda db:(seen.append(db) or dict(saved)))
    monkeypatch.setattr(runner,'source_rows',lambda:source)
    monkeypatch.setattr(runner,'running_containers',lambda:['pg-dpr'])
    monkeypatch.setattr(runner,'load_keys',lambda *a:({},{}))
    monkeypatch.setattr(runner,'PlaintextAdapter',MagicMock())
    monkeypatch.setattr(runner,'environment',lambda *a:{'database':a[-1]})
    monkeypatch.setattr(runner,'parameters',lambda *a,**k:{})
    monkeypatch.setattr(runner.psycopg,'connect',MagicMock())
    monkeypatch.setattr(runner,'one_run',lambda adapter,scenario,run,*a:{**summarize([1,2,3],0,1),
        'scenario':scenario,'run':run,'warmup_errors':0,'resources':{'samples':1,'failed_samples':0}})
    report=runner.baseline_run(database='baseline_1m')
    assert report['status']=='PASSED' and len(report['median_between_runs'])==7
    assert set(seen)=={'baseline_1m'} and len(seen)==23
    assert original.read_text()=='original 100k evidence'
    assert (tmp_path/'results/bench/before_1m/summary.csv').exists()


def test_1m_restore_dump_target_and_cleanup_are_isolated(monkeypatch,tmp_path,source):
    monkeypatch.setattr(common,'ROOT',tmp_path)
    monkeypatch.setattr(common,'require_disk_space',lambda:20_000_000_000)
    monkeypatch.setattr(backup,'private_directory',lambda:tmp_path)
    monkeypatch.setattr(backup,'running_containers',lambda:['pg-dpr'])
    saved={'rows':1000000,'checksum_sha256':'digest','sequence':{'last_value':1000000,'is_called':True}}
    monkeypatch.setattr(backup,'state',lambda *a,**k:dict(saved))
    monkeypatch.setattr(backup,'source_rows',lambda:source)
    monkeypatch.setattr(backup,'parameters',lambda *a,**k:{})
    monkeypatch.setattr(backup,'provenance',lambda:{})
    monkeypatch.setattr(backup.psycopg,'connect',MagicMock())
    def execute(cmd,**kwargs):
        if 'pg_dump' in cmd:
            assert cmd[-1]=='baseline_1m'
            kwargs['stdout'].write(b'PGDMP-handmade-fixture')
        else:
            assert 'pg_restore' in cmd and cmd[-1].startswith('bench_restore_')
    monkeypatch.setattr(backup.subprocess,'run',execute)
    report=backup.backup_restore(database='baseline_1m')
    assert report['database']=='baseline_1m' and report['status']=='PASSED'
    assert all(row['restored_rows']==1000000 and row['temporary_database_removed'] for row in report['runs'])
    assert not list(tmp_path.glob('*.dump'))


def test_private_script_is_parameterized_and_restores_leading_zeros():
    values=['01000000000001','01000000000002','01000000000003']
    expression=pg.key_expression(values)
    assert 'CASE WHEN :key_index < 1' in expression
    script=pg.custom_script([{'no_ktp':v} for v in values])
    assert "WHERE no_ktp=lpad(:nik::text,14,'0')" in script
    assert '\\set key_index random(0,2)' in script
    for invalid in ([],['bad'],['123']):
        with pytest.raises(ValueError):pg.key_expression(invalid)


def test_pgbench_output_and_logs_validate_counts(tmp_path):
    output='number of transactions actually processed: 2\nnumber of failed transactions: 0 (0%)\nlatency average = 1.500 ms\ntps = 4.000 (without initial connection time)'
    totals=pg.parse_output(output)
    log=tmp_path/'log';log.write_text('0 0 1000 0 1700000000 1\n1 0 2000 0 1700000000 2\n')
    assert pg.transaction_metrics([log],totals)['p95_ms']==1.95
    with pytest.raises(ValueError):pg.parse_output('incomplete')
    with pytest.raises(ValueError):pg.transaction_metrics([log],dict(totals,requests=3))
    log.write_text('unknown format')
    with pytest.raises(ValueError):pg.transaction_metrics([log],totals)


@pytest.mark.parametrize('fail',[False,True])
def test_crosscheck_three_runs_share_original_keys_and_cleanup(monkeypatch,tmp_path,source,fail):
    monkeypatch.setattr(pg,'ROOT',tmp_path)
    private=tmp_path/'private';private.mkdir()
    (tmp_path/'benchmark').mkdir()
    (tmp_path/'benchmark/workloads.yaml').write_text(json.dumps(MANIFEST))
    original=tmp_path/'evidence/benchmark/baseline';original.mkdir(parents=True)
    (original/'env.json').write_text(json.dumps({'key_corpus':{'sha256':'same'}}))
    metric={'p50_ms':1,'p95_ms':2,'mean_ms':1.5,'throughput_rps':4,'error_rate':0}
    (original/'summary.json').write_text(json.dumps({'median_between_runs':[{'scenario':'read_by_nik',**metric}]}))
    monkeypatch.setattr(pg,'load_keys',lambda *a:({'profiles':[{'no_ktp':'01000000000001'},{'no_ktp':'01000000000002'}]}, {'sha256':'same'}))
    monkeypatch.setattr(pg,'PlaintextAdapter',MagicMock())
    monkeypatch.setattr(pg,'private_directory',lambda:private)
    monkeypatch.setattr(pg,'state',lambda:{'rows':100000,'checksum_sha256':'same','sequence':{}})
    monkeypatch.setattr(pg,'running_containers',lambda:['pg-dpr'])
    secret=secrets.token_urlsafe(24)
    monkeypatch.setattr(pg,'parameters',lambda:{'password':secret})
    def execute(cmd,**kwargs):
        assert secret not in ' '.join(cmd)
        if fail:
            raise RuntimeError('private fake token')
        if 'pgbench' in cmd:
            return SimpleNamespace(stdout=b'number of transactions actually processed: 2\nnumber of failed transactions: 0\nlatency average = 1.500 ms\ntps = 4.000\n')
        if 'find' in cmd:
            prefix=cmd[-1][:-2]
            return SimpleNamespace(stdout='/tmp/'+prefix+'.123\n')
        if 'cp' in cmd:
            from pathlib import Path
            Path(cmd[-1]).write_text('0 0 1000 0 1700000000 1\n1 0 2000 0 1700000000 2\n')
        return SimpleNamespace(stdout='')
    monkeypatch.setattr(pg.subprocess,'run',execute)
    if fail:
        with pytest.raises(RuntimeError):pg.crosscheck()
        report=json.loads((tmp_path/'evidence/benchmark/crosscheck_pgbench.json').read_text())
        assert report['status']=='FAILED' and report['failure']['phase']=='warmup'
        assert report['private_temporary_script_removed'] and not list(private.iterdir())
        assert 'private fake token' not in json.dumps(report)
        return
    report=pg.crosscheck()
    assert report['status']=='PASSED' and len(report['runs'])==3
    assert report['private_temporary_script_removed'] and not list(private.iterdir())
    assert report['lookup_pool_matches_original_python'] and secret not in json.dumps(report)
    with pytest.raises(ValueError):pg.crosscheck()
    with pytest.raises(ValueError):pg.crosscheck(runs=1)
