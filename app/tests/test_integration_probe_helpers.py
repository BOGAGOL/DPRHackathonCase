"""Cleanup/target guards for the disposable integration probe."""
import importlib.util
from pathlib import Path
import sys
from uuid import uuid4

import pytest


def load_probe():
    path = Path(__file__).resolve().parents[1] / "scripts/integration_probe.py"
    spec = importlib.util.spec_from_file_location("service_integration_probe_under_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_disposable_probe_accepts_only_random_owned_names():
    probe = load_probe()
    suffix = uuid4().hex[:12]
    project, database = "dpr-b-probe-" + suffix, "dpr_b_test_" + suffix
    assert probe.validated_project(project) == project
    assert probe.validated_database(database) == database


@pytest.mark.parametrize("value", ["postgres", "baseline_100k", "protected_100k", "protected_734", "dpr-infra", "pg-dpr",
                                  "dpr-b-probe-../../pg-dpr", "dpr-b-probe-ABCDEF123456", "dpr-b-probe-0123456789abc",
                                  " dpr-b-probe-0123456789ab", "dpr-b-probe-0123456789ab\n"])
def test_probe_cannot_clean_shared_or_ambiguous_projects(value):
    with pytest.raises(ValueError):
        load_probe().validated_project(value)


@pytest.mark.parametrize("value", ["postgres", "baseline_100k", "protected_100k", "protected_734", "dpr_b_test_../../postgres",
                                  "dpr_b_test_ABCDEF123456", "dpr_b_test_0123456789abc", " dpr_b_test_0123456789ab",
                                  "dpr_b_test_0123456789ab\n"])
def test_probe_cannot_target_source_or_shared_databases(value):
    with pytest.raises(ValueError):
        load_probe().validated_database(value)


def test_probe_compose_requires_external_random_credentials_and_tls():
    source = (Path(__file__).resolve().parents[1] / "scripts/integration.compose.yaml").read_text(encoding="utf-8")
    assert "POSTGRES_DB: ${DPR_B_PROBE_DATABASE:?" in source
    assert "POSTGRES_PASSWORD: ${DPR_B_PROBE_ADMIN_PASSWORD:?" in source
    assert "source: ${DPR_B_PROBE_TLS:?" in source
    assert "ssl=on" in source and "ssl_cert_file=" in source and "ssl_key_file=" in source
    assert "log_statement=none" in source and "log_parameter_max_length_on_error=0" in source
    assert '127.0.0.1:0:5432' in source
    assert "create_host_path: false" in source
    assert "baseline_100k" not in source and "protected_100k" not in source and "pg-dpr" not in source


def test_live_https_accepts_default_auth_database_without_nonstring_env(monkeypatch, tmp_path):
    from types import SimpleNamespace
    probe = load_probe()
    monkeypatch.setattr(probe, "APP", tmp_path)
    (tmp_path / "web/.next").mkdir(parents=True)
    (tmp_path / "web/scripts").mkdir()
    (tmp_path / "web/.next/BUILD_ID").touch()
    (tmp_path / "web/scripts/live-probe.mjs").touch()
    monkeypatch.setattr(probe.shutil, "which", lambda name: "node")
    ports = iter([3443, 8100])
    monkeypatch.setattr(probe, "free_loopback_port", lambda: next(ports))
    settings = SimpleNamespace(database_url="test-primary-database", auth_database_url=None,
                               analyst_database_url="test-analyst-database", auditor_database_url="test-auditor-database")
    def capture(*args, **kwargs):
        assert kwargs["env"]["AUTH_DATABASE_URL"] == settings.database_url
        assert all(isinstance(value, str) for value in kwargs["env"].values())
        raise RuntimeError("STOP BEFORE NETWORK")
    monkeypatch.setattr(probe.subprocess, "Popen", capture)
    with pytest.raises(RuntimeError, match="STOP BEFORE NETWORK"):
        probe.exercise_live_https(settings, {}, tmp_path, {})
