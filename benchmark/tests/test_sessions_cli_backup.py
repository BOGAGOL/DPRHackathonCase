import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from benchmark import runner
from benchmark import backup_restore as backup
from benchmark import __main__ as cli
from benchmark.stats import summarize


MANIFEST = {"seed":42,"key_pool":40,"page_pool":1,"page_size":50,
            "scenarios":["read_by_nik","read_by_email","read_profile","list_page","update_contact","insert_member","mixed"],
            "mixed_cycle":{"read_by_nik":20,"read_by_email":20,"read_profile":20,"list_page":10,"update_contact":15,"insert_member":15}}
STATE = {"rows":100000,"checksum_sha256":"aggregate","sequence":{"last_value":100000,"is_called":True},"storage":{}}


def test_initial_session_all_runs_and_aggregate_outputs(monkeypatch,tmp_path,source):
    (tmp_path / "benchmark").mkdir()
    (tmp_path / "benchmark/workloads.yaml").write_text(json.dumps(MANIFEST))
    (tmp_path / "evidence/datasets").mkdir(parents=True)
    (tmp_path / "evidence/datasets/baseline_100k.json").write_text(json.dumps({"baseline_checksum_sha256":"aggregate"}))
    monkeypatch.setattr(runner,"ROOT",tmp_path)
    monkeypatch.setattr(runner,"RAW",tmp_path / "raw")
    monkeypatch.setattr(runner,"EVIDENCE",tmp_path / "evidence/benchmark")
    monkeypatch.setattr(runner,"running_containers",lambda:["pg-dpr"])
    monkeypatch.setattr(runner,"state",lambda *a:dict(STATE))
    monkeypatch.setattr(runner,"source_rows",lambda:source)
    monkeypatch.setattr(runner,"load_keys",lambda *a: ({},{}))
    monkeypatch.setattr(runner,"PlaintextAdapter",MagicMock())
    monkeypatch.setattr(runner,"environment",lambda *a: {"session_kind":"baseline_awal"})
    monkeypatch.setattr(runner,"parameters",lambda *a,**k: {})
    monkeypatch.setattr(runner.psycopg,"connect",MagicMock())
    def fake_run(adapter,scenario,run,*args):
        return {**summarize([1,2,3],0,1),"scenario":scenario,"run":run,"warmup_errors":0,"resources":{"samples":1,"failed_samples":0}}
    monkeypatch.setattr(runner,"one_run",fake_run)
    result=runner.baseline_run()
    assert result["status"]=="PASSED" and len(result["median_between_runs"])==7
    saved=json.loads((tmp_path / "raw/run_summaries.json").read_text())
    assert len(saved)==21 and all(r["data_and_sequence_unchanged"] for r in saved)
    assert all(row["p95_ms"]==2.9 for row in result["median_between_runs"])
    assert not any(row["email"] in (tmp_path / "raw/summary.json").read_text() for row in source)


def test_environment_without_exposing_inspect_env(monkeypatch,tmp_path):
    (tmp_path / "benchmark").mkdir()
    (tmp_path / "benchmark/workloads.yaml").write_text(json.dumps(MANIFEST))
    monkeypatch.setattr(runner,"ROOT",tmp_path)
    conn=MagicMock(); conn.__enter__.return_value=conn
    conn.execute.return_value.fetchone.side_effect=[(False,),("18.6",),("bench_user",)]
    conn.execute.return_value.fetchall.return_value=[("shared_buffers","16384")]
    monkeypatch.setattr(runner.psycopg,"connect",lambda **k:conn)
    monkeypatch.setattr(runner,"parameters",lambda *a,**k:{})
    monkeypatch.setattr(runner,"provenance",lambda:{"targets_commit":"a"*40})
    monkeypatch.setattr(runner,"running_containers",lambda:["pg-dpr"])
    def call(cmd,**kwargs):
        if cmd[:2]==["docker","inspect"]:
            return SimpleNamespace(stdout=json.dumps([{"Config":{"Image":"postgres:18","Env":["not-to-export"]},
                "Image":"sha256:image","HostConfig":{"Memory":0,"NanoCpus":0}}]))
        return SimpleNamespace(stdout="hardware version metadata only")
    monkeypatch.setattr(runner.subprocess,"run",call)
    result=runner.environment(MANIFEST,{},STATE,{})
    assert result["session_kind"]=="baseline_awal" and not result["tls"]
    assert "not-to-export" not in json.dumps(result)
    assert "5434" in result["team_decision"]["excluded"][0]


def test_backup_three_new_databases_checksum_cleanup_and_safe_names(monkeypatch,tmp_path,source):
    monkeypatch.setattr(backup,"RAW",tmp_path / "raw")
    monkeypatch.setattr(backup,"EVIDENCE",tmp_path / "evidence")
    monkeypatch.setattr(backup,"private_directory",lambda:tmp_path)
    monkeypatch.setattr(backup,"state",lambda *a,**k:dict(STATE))
    monkeypatch.setattr(backup,"source_rows",lambda:source)
    monkeypatch.setattr(backup,"provenance",lambda:{"targets_commit":"a"*40})
    monkeypatch.setattr(backup,"parameters",lambda *a,**k:{})
    monkeypatch.setattr(backup,"running_containers",lambda:["pg-dpr"])
    conn=MagicMock(); conn.__enter__.return_value=conn
    monkeypatch.setattr(backup.psycopg,"connect",lambda **k:conn)
    def call(cmd,**kwargs):
        if "pg_dump" in cmd:
            kwargs["stdout"].write(b"PGDMP"+b"synthetic-archive")
        else:
            assert "pg_restore" in cmd and "baseline_100k" not in cmd and "postgres" in cmd
    monkeypatch.setattr(backup.subprocess,"run",call)
    result=backup.backup_restore()
    assert result["status"]=="PASSED" and len(result["runs"])==3
    names=[row["temporary_database"] for row in result["runs"]]
    assert len(set(names))==3 and all(backup.guard_restore(n)==n for n in names)
    assert all(row["restored_rows"]==100000 and row["temporary_database_removed"] for row in result["runs"])
    assert not list(tmp_path.glob("*.dump"))
    drops=[c.args[0].as_string() for c in conn.execute.call_args_list if "DROP DATABASE" in c.args[0].as_string()]
    assert len(drops)==3 and all("baseline_100k" not in s for s in drops)
    for invalid in ("postgres","baseline_100k","bench_restore_1_abc;DROP"):
        with pytest.raises(ValueError): backup.guard_restore(invalid)
    with pytest.raises(ValueError): backup.backup_restore(1)
    with pytest.raises(ValueError): backup.backup_restore()


def test_backup_failure_preserves_own_artifact_and_exports_no_driver_details(monkeypatch,tmp_path,source):
    monkeypatch.setattr(backup,"RAW",tmp_path / "raw")
    monkeypatch.setattr(backup,"EVIDENCE",tmp_path / "evidence")
    monkeypatch.setattr(backup,"private_directory",lambda:tmp_path)
    monkeypatch.setattr(backup,"state",lambda *a,**k:dict(STATE))
    monkeypatch.setattr(backup,"source_rows",lambda:source)
    monkeypatch.setattr(backup,"running_containers",lambda:["pg-dpr"])
    monkeypatch.setattr(backup.subprocess,"run",MagicMock(side_effect=RuntimeError("private driver payload")))
    with pytest.raises(RuntimeError): backup.backup_restore()
    result=(tmp_path / "evidence/backup_restore.json").read_text()
    assert "private driver payload" not in result and '"FAILED"' in result


def test_cli_commands_and_generic_errors(monkeypatch,tmp_path,capsys):
    monkeypatch.setattr(cli,"EVIDENCE",tmp_path)
    run=MagicMock(return_value={"status":"PASSED"})
    monkeypatch.setattr(cli,"baseline_run",run)
    monkeypatch.setattr(cli,"backup_restore",MagicMock(return_value={"status":"PASSED"}))
    assert cli.main(["run"])==0 and cli.main(["backup-restore"])==0
    assert run.call_args.args==(3,60,8,10,"all")
    assert run.call_args.kwargs=={"database":"baseline_100k"}
    run.side_effect=RuntimeError("private driver text")
    assert cli.main(["run"])==2
    assert "private driver text" not in capsys.readouterr().err
    assert "private driver text" not in (tmp_path / "failure.json").read_text()
