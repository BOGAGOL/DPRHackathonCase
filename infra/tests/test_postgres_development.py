import json
import os
from pathlib import Path
import subprocess
from unittest.mock import MagicMock, Mock

import pytest

from datagen import database
from datagen.model import COLUMNS
from infra.postgres import credentials, development as dev


def synthetic_dump(path: Path, suffix: str = "") -> None:
    columns = ",".join(COLUMNS[1:])
    values = ["NULL" if column == "tanggal_pernikahan" else "'Uji''Contoh'" for column in COLUMNS[1:]]
    statement = "INSERT INTO anggota (" + columns + ") VALUES (" + ",".join(values) + ");\n"
    path.write_text("BEGIN;\n" + statement * 2 + "COMMIT;\n" + suffix, encoding="utf-8")


def test_source_parser_does_not_execute_sql_and_preserves_literals(tmp_path):
    path = tmp_path / "synthetic.sql"
    synthetic_dump(path)
    rows = dev.read_source(path, expected_rows=2)
    assert len(rows) == 2 and rows[0]["nama"] == "Uji'Contoh" and rows[0]["tanggal_pernikahan"] is None
    with pytest.raises(ValueError):
        dev.read_source(path)
    synthetic_dump(path, "DROP TABLE anggota;\n")
    with pytest.raises(ValueError):
        dev.read_source(path, expected_rows=2)
    synthetic_dump(path)
    path.write_text(path.read_text().replace("INTO anggota", "INTO users"))
    with pytest.raises(ValueError):
        dev.read_source(path, expected_rows=2)


def test_windows_dpapi_roundtrip_and_no_plaintext_credential_file(tmp_path):
    if os.name != "nt":
        pytest.skip("DPAPI helper is Windows-specific")
    password = os.urandom(32).hex()
    credentials.save_password(tmp_path, password)
    serialized = (tmp_path / "postgres/admin.credential.xml").read_text()
    assert password not in serialized and "<SS " in serialized
    assert credentials.load_password(tmp_path) == password
    with pytest.raises(FileExistsError):
        credentials.save_password(tmp_path, password)


def test_credential_errors_are_sanitized(tmp_path, monkeypatch):
    monkeypatch.setattr(credentials.subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 1, "", "private")))
    with pytest.raises(RuntimeError, match="output withheld"):
        credentials.powershell("", {})
    monkeypatch.setattr(credentials, "powershell", Mock(return_value="plaintext"))
    with pytest.raises(RuntimeError):
        credentials.save_password(tmp_path, "plaintext")
    credentials.powershell.return_value = ""
    with pytest.raises(RuntimeError):
        credentials.load_password(tmp_path)


def test_create_uses_named_pg18_volume_env_password_and_refuses_existing_container(tmp_path, monkeypatch):
    monkeypatch.delenv("DPR_DOCKER_CONTEXT", raising=False)
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    run = Mock(side_effect=[subprocess.CompletedProcess([], 1, "", ""), subprocess.CompletedProcess([], 1, "", "")])
    monkeypatch.setattr(dev.subprocess, "run", run)
    monkeypatch.setattr(dev.socket, "socket", MagicMock())
    docker = Mock(side_effect=lambda args, **kwargs: json.dumps("npipe:////./pipe/dockerDesktopLinuxEngine") if args[0] == "context" else "18.6")
    monkeypatch.setattr(dev, "docker", docker)
    save = Mock()
    monkeypatch.setattr(dev, "save_password", save)
    target = Mock()
    target.metadata.return_value = {"version": 180006}
    monkeypatch.setattr(dev, "ExistingPostgres", Mock(return_value=target))
    result = dev.create_container(tmp_path)
    assert result["port"] == 5433 and result["persistent_volume"] == "pg-dpr-data"
    run_call = next(call for call in docker.call_args_list if call.args[0][0] == "run")
    assert run_call.args[0][-1] == "postgres:18"
    assert "POSTGRES_PASSWORD" in run_call.args[0]
    assert run_call.kwargs["environment"]["POSTGRES_PASSWORD"] not in " ".join(run_call.args[0])
    run.side_effect = None
    run.return_value = subprocess.CompletedProcess([], 0, "[]", "")
    with pytest.raises(RuntimeError, match="refusing to recreate"):
        dev.create_container(tmp_path)
    run.reset_mock()
    docker.side_effect = lambda *args, **kwargs: json.dumps("ssh://example.test")
    with pytest.raises(RuntimeError, match="local Docker context"):
        dev.create_container(tmp_path)
    assert not run.called


def test_parameters_and_source_validation_only_use_verified_tls(tmp_path, monkeypatch):
    monkeypatch.setattr(dev, "load_password", Mock(return_value=os.urandom(24).hex()))
    params = dev.parameters(tmp_path, "postgres")
    assert params["port"] == 5433 and params["sslmode"] == "verify-full"
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.execute.return_value.fetchone.return_value = (734, 734, 14, 14, 367, 367)
    monkeypatch.setattr(dev.psycopg, "connect", Mock(return_value=connection))
    assert dev.validate_source(tmp_path)["passed"]
    assert connection.execute.call_args_list[0].args[0] == "SET TRANSACTION READ ONLY"
    connection.execute.return_value.fetchone.return_value = (734, 733, 14, 14, 367, 367)
    assert not dev.validate_source(tmp_path)["passed"]


def test_import_fences_existing_source_and_uses_bound_inserts(tmp_path, monkeypatch):
    path = tmp_path / "synthetic.sql"
    synthetic_dump(path)
    rows = dev.read_source(path, expected_rows=2)
    monkeypatch.setattr(dev, "read_source", Mock(return_value=rows))
    monkeypatch.setattr(dev, "parameters", Mock(return_value={}))
    monkeypatch.setattr(dev, "validate_source", Mock(return_value={"passed": True}))
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.execute.return_value.fetchone.return_value = (None,)
    monkeypatch.setattr(dev.psycopg, "connect", Mock(return_value=connection))
    assert dev.import_source(tmp_path, path)["passed"]
    assert connection.cursor.return_value.__enter__.return_value.executemany.called
    connection.execute.return_value.fetchone.return_value = ("anggota",)
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        dev.import_source(tmp_path, path)


def test_empty_targets_create_only_missing_names(tmp_path, monkeypatch):
    monkeypatch.setattr(dev, "parameters", Mock(return_value={}))
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.execute.return_value.fetchone.side_effect = [None, (1,)]
    monkeypatch.setattr(dev.psycopg, "connect", Mock(return_value=connection))
    assert dev.create_empty_targets(tmp_path) == ["protected_734"]


def test_development_baseline_sink_never_overwrites_official_evidence(tmp_path, monkeypatch):
    expected = "0" * 64
    official = tmp_path / "evidence/datasets/baseline_100k.json"
    official.parent.mkdir(parents=True)
    official.write_text(json.dumps({"baseline_checksum_sha256": expected}))
    before = official.read_bytes()
    monkeypatch.setattr(dev, "REPO", tmp_path)
    monkeypatch.setattr(dev, "parameters", Mock(return_value={"host": "127.0.0.1", "port": 5433}))
    def build(name, rows, seed, anomalies):
        payload = {"baseline_checksum_sha256": expected}
        database.record(name, payload)
        return payload
    monkeypatch.setattr(database, "build", build)
    original_sink = database.record
    monkeypatch.setenv("DATAGEN_DATABASE_URL", "previous-value")
    result = dev.generate_baseline(tmp_path)
    assert result["matches_official_checksum"] and official.read_bytes() == before
    assert not json.loads((tmp_path / "evidence/development/baseline_100k.json").read_text())["official_benchmark"]
    assert database.record is original_sink and os.environ["DATAGEN_DATABASE_URL"] == "previous-value"


def test_verify_rehashes_source_and_baseline_with_read_only_transactions(tmp_path, monkeypatch):
    official = tmp_path / "evidence/datasets/baseline_100k.json"
    official.parent.mkdir(parents=True)
    official.write_text(json.dumps({"validation": {"source_checksum_sha256": "synthetic-source"}, "baseline_checksum_sha256": "synthetic-baseline"}))
    monkeypatch.setattr(dev, "REPO", tmp_path)
    monkeypatch.setattr(dev, "parameters", Mock(return_value={}))
    monkeypatch.setattr(dev, "checksum", Mock(side_effect=["synthetic-source", "synthetic-baseline"]))
    connections = []
    for count in (734, 100000, 0, 0):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.execute.return_value.fetchone.side_effect = [{"ssl": True, "version": "TLSv1.3"}, {"rows": count, "tables": count}]
        connections.append(connection)
    monkeypatch.setattr(dev.psycopg, "connect", Mock(side_effect=connections))
    result = dev.verify_development(tmp_path)
    assert result["passed"] and all(result["checks"].values())
    assert all(connection.execute.call_args_list[0].args[0] == "SET TRANSACTION READ ONLY" for connection in connections)


@pytest.mark.parametrize("command", ["create", "import-source", "validate-source", "baseline", "empty-targets", "verify"])
def test_development_cli_records_scope_and_status(tmp_path, monkeypatch, command):
    monkeypatch.setattr(dev, "REPO", tmp_path)
    monkeypatch.setenv("DPR_SECRETS_DIR", str(tmp_path / "private"))
    monkeypatch.setattr("sys.argv", ["development", command])
    for name in ("create_container", "import_source", "validate_source", "generate_baseline", "verify_development"):
        monkeypatch.setattr(dev, name, Mock(return_value={"passed": True}))
    monkeypatch.setattr(dev, "create_empty_targets", Mock(return_value=[]))
    dev.main()
    report = json.loads((tmp_path / "evidence/development" / (command + ".json")).read_text())
    assert report["passed"] and not report["official_benchmark"]
    monkeypatch.setenv("DPR_SECRETS_DIR", "relative")
    with pytest.raises(SystemExit):
        dev.main()


def test_docker_helper_does_not_print_error_output(monkeypatch):
    monkeypatch.setattr(dev.subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 1, "", "private")))
    with pytest.raises(RuntimeError, match="output withheld"):
        dev.docker(["info"])
