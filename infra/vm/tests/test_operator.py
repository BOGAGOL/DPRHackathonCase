import json
import os
from pathlib import Path
import secrets
import shlex
from unittest.mock import MagicMock

import pytest
import yaml

from infra.security import REPO, secure_directory, write_private
from infra.vm import operator as vm


@pytest.fixture
def material(tmp_path,monkeypatch):
    root=secure_directory(tmp_path/"private")
    monkeypatch.delenv("DPR_VM_PROJECT",raising=False)
    monkeypatch.delenv("PGPORT",raising=False)
    vm.initialize_credentials(root,1000,1000)
    return root


def read_env(path):
    return dict(token.split("=",1) for token in shlex.split(path.read_text()))


def test_credentials_are_random_preserved_and_scoped(material):
    before=vm.credentials(material)
    assert set(before)==set(vm.PASSWORD_NAMES) and len(set(before.values()))==8
    vm.initialize_credentials(material,1000,1000)
    assert vm.credentials(material)==before
    operator=read_env(material/"operator.env")
    assert operator["DPR_POSTGRES_CONTAINER"]=="dpr-demo-postgres-1"
    assert operator["PGPASSWORD"]==before["PGPASSWORD"]
    assert "OPENBAO_TOKEN" not in operator
    assert not any(secret in (material/"compose.env").read_text() for secret in before.values())
    assert (material/"postgres-password").read_text().strip()==before["PGPASSWORD"]
    with pytest.raises(ValueError):vm.initialize_credentials(material,1001,1000)


@pytest.mark.parametrize("uid,gid",[(0,1000),(1000,0),(-1,1000),(True,1000),(1000,2**32)])
def test_unsafe_runtime_ids_refused_before_writes(tmp_path,uid,gid):
    with pytest.raises(ValueError): vm.initialize_credentials(tmp_path,uid,gid)
    assert not list(tmp_path.iterdir())


def test_bad_project_and_incomplete_material_refused(tmp_path,monkeypatch):
    monkeypatch.setenv("DPR_VM_PROJECT","other-team")
    with pytest.raises(ValueError): vm.initialize_credentials(tmp_path,1000,1000)
    assert not list(tmp_path.iterdir())
    monkeypatch.delenv("DPR_VM_PROJECT")
    write_private(tmp_path/"postgres-password",secrets.token_bytes(32))
    with pytest.raises(ValueError): vm.initialize_credentials(tmp_path,1000,1000)


def test_bad_private_json_credentials_and_password_disagreement(material):
    p=material/"database-credentials.json"
    original=p.read_bytes()
    p.write_text("{}")
    with pytest.raises(ValueError): vm.credentials(material)
    p.write_bytes(original)
    (material/"postgres-password").write_text(secrets.token_urlsafe(36))
    with pytest.raises(ValueError): vm.initialize_credentials(material,1000,1000)
    with pytest.raises(ValueError): vm.private_json(material/"missing")


def test_shell_environment_quoting_and_invalid_names(material):
    path=material/"quoted.env"
    value="a' ; $(must-not-run)\nnext line"
    vm.save_environment(path,{"VALUE":value})
    assert read_env(path)=={"VALUE":value}
    with pytest.raises(ValueError): vm.save_environment(path,{"BAD;echo":value})
    assert read_env(path)=={"VALUE":value}


def test_database_parameters_use_env_credentials_tls_and_readonly(material,monkeypatch):
    params=vm.database_parameters(material,"postgres","scanner_user",True)
    assert params["user"]=="scanner_user" and params["sslmode"]=="verify-full"
    assert params["options"]=="-c default_transaction_read_only=on"
    assert "panic" in vm.database_parameters(material,"protected_734")["options"]
    monkeypatch.setenv("PGPORT","5434")
    with pytest.raises(ValueError): vm.endpoints(material)


def seed_tokens(root):
    folder=secure_directory(root/"openbao/tokens")
    result={}
    for policy in ("svc-app","svc-migration"):
        result[policy]=secrets.token_urlsafe(32)
        write_private(folder/(policy+"-20261028.json"),json.dumps({"auth":{"client_token":result[policy]}}).encode())
    return result


def test_workload_environment_does_not_copy_bootstrap_credentials(material):
    values=seed_tokens(material)
    assert vm.workload_environment(material)["passed"]
    env=read_env(material/"migration.env")
    assert env["OPENBAO_MIGRATION_TOKEN"]==values["svc-migration"]
    assert "PGPASSWORD" not in env and "OPENBAO_TOKEN" not in env and "DPR_APP_USER_PASSWORD" not in env
    with pytest.raises(ValueError): vm.token(material,"root")
    with pytest.raises(ValueError): vm.token(material/"missing","svc-app")


def test_token_selection_uses_creation_time_not_random_filename_suffix(material):
    folder=secure_directory(material/"openbao/tokens")
    old=folder/"svc-app-20261028T100000Z-zzzz.json"
    new=folder/"svc-app-20261028T100000Z-aaaa.json"
    old_token=secrets.token_urlsafe(32);new_token=secrets.token_urlsafe(32)
    for path,value in ((old,old_token),(new,new_token)):
        write_private(path,json.dumps({"auth":{"client_token":value}}).encode())
    os.utime(old,ns=(1000000000,1000000000));os.utime(new,ns=(2000000000,2000000000))
    assert vm.token(material,"svc-app")==new_token


def test_service_identity_is_scoped_and_restored_on_failure(material,monkeypatch):
    seed_tokens(material)
    previous=secrets.token_urlsafe(32)
    monkeypatch.setenv("DPR_VM_SVC_APP_TOKEN",previous)
    client=MagicMock();client.__enter__.return_value=client
    monkeypatch.setattr(vm,"OpenBaoClient",lambda **kwargs:client)
    with pytest.raises(RuntimeError):
        with vm.service_client(material):
            assert os.environ["DPR_VM_SVC_APP_TOKEN"]!=previous
            raise RuntimeError("Invented downstream failure")
    assert os.environ["DPR_VM_SVC_APP_TOKEN"]==previous


def test_bootstrap_uses_root_only_for_explicit_operator_action(material,monkeypatch):
    root_token=secrets.token_urlsafe(32)
    directory=secure_directory(material/"openbao")
    write_private(directory/"init-material.json",json.dumps({"root_token":root_token}).encode())
    api=object(); configure=MagicMock(); issue=MagicMock()
    monkeypatch.setattr(vm,"from_environment",lambda:api)
    monkeypatch.setattr(vm,"configure",configure);monkeypatch.setattr(vm,"issue_tokens",issue)
    assert vm.bootstrap_bao(material,14400)["passed"]
    configure.assert_called_once_with(api,root_token)
    issue.assert_called_once_with(api,root_token,material,14400)
    configure.reset_mock()
    with pytest.raises(ValueError): vm.bootstrap_bao(material,14401)
    configure.assert_not_called()
    api=MagicMock();api.request.return_value={"auth":{"client_token":secrets.token_urlsafe(32)}}
    monkeypatch.setattr(vm,"from_environment",lambda:api)
    assert vm.bootstrap_bao(material,3600,app_only=True)["app_only"]
    configure.assert_not_called()
    payload=api.request.call_args.args[1]
    assert payload["policies"]==["svc-app"] and payload["explicit_max_ttl"]=="3600s"
    assert len(list((material/"openbao/tokens").glob("svc-app-*.json")))==1


def test_handoff_separates_operator_secrets_and_runtime(material,monkeypatch):
    tokens=seed_tokens(material)
    client=MagicMock();client.__enter__.return_value=client
    monkeypatch.setattr(vm,"OpenBaoClient",lambda **kwargs:client)
    connection=MagicMock();connection.__enter__.return_value=connection
    principal="invented-principal-"+secrets.token_hex(5)
    connection.execute.return_value.fetchone.return_value=(principal,)
    monkeypatch.setattr(vm.psycopg,"connect",lambda **kwargs:connection)
    assert vm.handoff(material,"https://demo.example.invalid")["passed"]
    app=read_env(material/"handoff/app.env");setup=read_env(material/"handoff/setup.env")
    assert app["OPENBAO_TOKEN"]==tokens["svc-app"] and setup["DEMO_MEMBER_PRINCIPAL"]==principal
    assert "APP_SETUP_DATABASE_URL" not in app and "DPR_PRIVATE_DIR" not in app
    assert all(value not in (material/"handoff/app.env").read_text() for key,value in vm.credentials(material).items() if key in {"PGPASSWORD","DPR_MIGRATION_USER_PASSWORD","DPR_SCANNER_USER_PASSWORD"})
    assert "postgresql+psycopg://postgres:" in setup["APP_SETUP_DATABASE_URL"]
    with pytest.raises(ValueError): vm.handoff(material,"http://demo.example.invalid")
    client.require_policy.assert_called_with("svc-app")


def test_retirement_requires_completed_job(material,monkeypatch):
    connection=MagicMock();connection.__enter__.return_value=connection
    connection.execute.return_value.fetchone.side_effect=[("validated","postgres",734,734),(734,)]
    monkeypatch.setattr(vm.psycopg,"connect",lambda **kwargs:connection)
    assert vm.retire_migration(material)["passed"]
    assert connection.execute.call_args.args[0]=="ALTER ROLE migration_user NOLOGIN"
    connection.reset_mock()
    connection.execute.return_value.fetchone.side_effect=[("running","postgres",734,100),(100,)]
    with pytest.raises(ValueError): vm.retire_migration(material)
    assert connection.execute.call_count==2


def test_initial_source_import_refuses_other_containers_and_existing_source(material,monkeypatch):
    monkeypatch.setattr(vm,"read_source",lambda path:[{"nama":"invented"}])
    target=MagicMock();target.info={"Config":{"Labels":{"dpr.scope":"other"}}}
    monkeypatch.setattr(vm,"ExistingPostgres",lambda container:target)
    with pytest.raises(ValueError):vm.import_source(material,Path("invented.sql"))
    target.info={"Config":{"Labels":{"dpr.scope":"vm-demo"}}};target.query.return_value="cluster"
    connection=MagicMock();connection.__enter__.return_value=connection
    connection.execute.return_value.fetchone.side_effect=[("cluster",),(123,)]
    monkeypatch.setattr(vm.psycopg,"connect",lambda **kwargs:connection)
    with pytest.raises(ValueError):vm.import_source(material,Path("invented.sql"))
    assert connection.execute.call_count==2


def test_fresh_import_never_executes_drop_and_grants_only_source_reader(material,monkeypatch,tmp_path):
    source=tmp_path/"source.sql";source.write_text("invented parser input")
    monkeypatch.setattr(vm,"read_source",lambda path:[{"nama":"Invented member"}])
    target=MagicMock();target.info={"Config":{"Labels":{"dpr.scope":"vm-demo"}}};target.query.return_value="cluster"
    monkeypatch.setattr(vm,"ExistingPostgres",lambda name:target)
    connection=MagicMock();connection.__enter__.return_value=connection
    results=[("cluster",),(None,),(734,734,14,14,367,367)]
    def execute(query,*args):
        if query.startswith(("SELECT system_identifier","SELECT to_regclass","SELECT count(*)")):
            return MagicMock(fetchone=lambda:results.pop(0))
        return MagicMock()
    connection.execute.side_effect=execute
    monkeypatch.setattr(vm.psycopg,"connect",lambda **kwargs:connection)
    assert vm.import_source(material,source)["source_rows"]==734
    statements=[str(call.args[0]) for call in connection.execute.call_args_list]
    assert all("DROP TABLE" not in statement for statement in statements)
    assert "GRANT SELECT ON public.anggota TO scanner_user" in statements
    assert not any("UPDATE ON public.anggota" in statement for statement in statements)


def test_changed_destructive_baseline_ddl_is_refused_before_execution(material,monkeypatch,tmp_path):
    monkeypatch.setattr(vm,"read_source",lambda path:[{"nama":"Invented member"}])
    target=MagicMock();target.info={"Config":{"Labels":{"dpr.scope":"vm-demo"}}};target.query.return_value="cluster"
    monkeypatch.setattr(vm,"ExistingPostgres",lambda name:target)
    connection=MagicMock();connection.__enter__.return_value=connection
    connection.execute.return_value.fetchone.side_effect=[("cluster",),(None,)]
    monkeypatch.setattr(vm.psycopg,"connect",lambda **kwargs:connection)
    (tmp_path/"sql/baseline").mkdir(parents=True)
    (tmp_path/"sql/baseline/01_schema.sql").write_text("DROP TABLE IF EXISTS anggota; DROP TABLE another_table;")
    monkeypatch.setattr(vm,"REPO",tmp_path)
    with pytest.raises(ValueError):vm.import_source(material,Path("invented.sql"))
    assert connection.execute.call_count==2


@pytest.mark.parametrize(("unsafe","analyst_safe"),[(False,True),(True,True),(False,False)])
def test_readonly_verifier_covers_all_rows_and_detects_bad_role_metadata(material,monkeypatch,unsafe,analyst_safe):
    seed_tokens(material)
    monkeypatch.setattr(vm,"load_profile",lambda path:{})
    compare=MagicMock();monkeypatch.setattr(vm,"compare_batch",compare)
    client=MagicMock();client.__enter__.return_value=client
    monkeypatch.setattr(vm,"OpenBaoClient",lambda **kwargs:client)
    api=MagicMock();api.request.side_effect=vm.BaoError(403)
    monkeypatch.setattr(vm,"from_environment",lambda:api)
    analyst_check=MagicMock(return_value={"analyst_no_per_record_select":analyst_safe})
    monkeypatch.setattr(vm,"analyst_security_checks",analyst_check)
    def connect(**parameters):
        role=parameters["user"];database=parameters["dbname"]
        assert parameters["options"]=="-c default_transaction_read_only=on"
        connection=MagicMock();connection.__enter__.return_value=connection
        def execute(query,*arguments):
            if query.startswith("SELECT *"):
                return MagicMock(fetchall=lambda:[{"id" if database=="postgres" else "legacy_row_id":i} for i in range(1,735)])
            if "FROM pg_roles" in query:
                rows=[(name,name not in {"schema_owner","migration_user"},unsafe,False,False,False,False) for name in ("schema_owner",*vm.ROLES)]
                return MagicMock(fetchall=lambda:rows)
            if "has_table_privilege" in query or "has_schema_privilege" in query: result=(False,)
            elif query.startswith("SELECT count(*)"):
                if role!="app_user": raise vm.psycopg.errors.InsufficientPrivilege("Synthetic denial")
                result=(0,)
            else: result=(True,)
            return MagicMock(fetchone=lambda:result)
        connection.execute.side_effect=execute
        return connection
    monkeypatch.setattr(vm.psycopg,"connect",connect)
    result=vm.verify(material)
    assert result["rows_compared"]==734 and compare.call_count==8
    assert result["passed"] is (not unsafe and analyst_safe)
    assert result["checks"]["migration_identity_rejected"]
    assert result["checks"]["analyst_no_per_record_select"] is analyst_safe
    analyst_check.assert_called_once()


def test_compose_keeps_tls_private_files_and_loopback_bindings():
    value=yaml.safe_load((REPO/"infra/vm/compose.yaml").read_text())
    services=value["services"]
    assert services["postgres"]["ports"]==["127.0.0.1:5433:5432"]
    assert "PASSWORD_FILE" in " ".join(services["postgres"]["environment"])
    assert services["openbao"]["image"]=="openbao/openbao:2.5.5"
    assert services["openbao"]["user"].startswith("${DPR_VM_UID")
    assert services["bao-volume"]["network_mode"]=="none"
    mounts=services["openbao"]["volumes"]
    assert not any('ca.key' in str(m) or 'init-material' in str(m) for m in mounts)


def test_cli_writes_only_nonsecret_machine_results(material,monkeypatch,capsys,tmp_path):
    monkeypatch.setenv("DPR_SECRETS_DIR",str(material))
    evidence=tmp_path/"evidence"
    assert vm.main(["init-secrets","--uid","1000","--gid","1000","--evidence-dir",str(evidence)])==0
    assert json.loads((evidence/"vm-init-secrets.json").read_text())["passed"]
    output=capsys.readouterr().out
    assert all(secret not in output for secret in vm.credentials(material).values())
    assert vm.main(["import-source","--evidence-dir",str(evidence)])==1
    assert json.loads((evidence/"vm-import-source.json").read_text())["error"]=="vm_operation_failed_details_withheld"
