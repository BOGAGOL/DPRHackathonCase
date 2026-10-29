import json
from types import SimpleNamespace
import sys
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import f01_identity as cli


@pytest.mark.parametrize('command', ['inspect', 'apply', 'verify'])
def test_cli_reports_metadata_only_and_applies_only_when_requested(monkeypatch, tmp_path, command):
    queries, applied = [], []
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, query): queries.append(query)
    monkeypatch.setattr(cli.Settings, 'from_env', lambda: SimpleNamespace(mode='protected'))
    monkeypatch.setenv('APP_SETUP_DATABASE_URL', 'provided-privately')
    monkeypatch.setattr(cli, 'setup_url', lambda *args: make_url('postgresql+psycopg://postgres@localhost/protected_734'))
    monkeypatch.setattr(cli.psycopg, 'connect', lambda *args, **kwargs: Connection())
    state = {'members': 734, 'pentest_duplicate_ids_remaining': 0,
             'duplicate_identity_groups': 0, 'unique_index_valid': command != 'apply'}
    monkeypatch.setattr(cli, 'identity_state', lambda connection: dict(state))
    monkeypatch.setattr(cli, 'apply_identity_unique', lambda connection: applied.append(True) or {**state, 'unique_index_valid': True})
    path = tmp_path / 'report.json'
    assert cli.main([command, '--evidence', str(path)]) == 0
    report = json.loads(path.read_text())
    assert report['passed'] and report['finding'] == 'F-01'
    assert report['member_values_written_to_evidence'] is False
    assert applied == ([True] if command == 'apply' else [])
    assert ('SET TRANSACTION READ ONLY' in queries) == (command != 'apply')


def test_cli_refuses_to_apply_before_golden_reset(monkeypatch, tmp_path):
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, query): pass
    monkeypatch.setattr(cli.Settings, 'from_env', lambda: SimpleNamespace(mode='protected'))
    monkeypatch.setenv('APP_SETUP_DATABASE_URL', 'provided-privately')
    monkeypatch.setattr(cli, 'setup_url', lambda *args: make_url('postgresql+psycopg://postgres@localhost/protected_734'))
    monkeypatch.setattr(cli.psycopg, 'connect', lambda *args, **kwargs: Connection())
    monkeypatch.setattr(cli, 'identity_state', lambda connection: {'members': 737, 'pentest_duplicate_ids_remaining': 2})
    monkeypatch.setattr(cli, 'apply_identity_unique', lambda connection: pytest.fail('Must not apply before reset'))
    path = tmp_path / 'report.json'
    assert cli.main(['apply', '--evidence', str(path)]) == 1
    assert json.loads(path.read_text())['error'] == 'f01_operation_failed_details_withheld'


def test_cli_sanitizes_configuration_failure(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv('APP_SETUP_DATABASE_URL', raising=False)
    monkeypatch.setattr(cli.Settings, 'from_env', lambda: SimpleNamespace(mode='protected'))
    path = tmp_path / 'failed.json'
    assert cli.main(['inspect', '--evidence', str(path)]) == 1
    assert json.loads(path.read_text())['passed'] is False
    assert 'traceback' not in capsys.readouterr().out.lower()
