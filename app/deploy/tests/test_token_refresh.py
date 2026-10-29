"""Invented credentials only. No connection to the team VM or databases."""
import importlib.util
import json
import os
from pathlib import Path
import secrets
import stat
from types import SimpleNamespace

import pytest

APP = Path(__file__).resolve().parents[2]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def broker():
    return load(APP / "deploy/token_refresh.py", "test_token_broker")


@pytest.fixture
def flow(broker, monkeypatch, tmp_path):
    # Windows tests exercise state transitions independently of Linux file ownership.
    # Actual ownership/TLS/API integration is also checked in a disposable Linux Bao.
    monkeypatch.setattr(broker, "private_read", lambda path, **kw: path.read_text())
    monkeypatch.setattr(broker, "private_write", lambda path, content, **kw: path.write_text(content))
    config = {"role_id": secrets.token_urlsafe(24), "secret_id": secrets.token_urlsafe(24),
              "ca": "invented-ca", "gid": 1000}
    old, fresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)

    class FakeAPI:
        def __init__(self):
            self.ttl = 14400
            self.new_ttl = 14400
            self.policies = ["svc-app"]
            self.identity_policies = []
            self.maximum = 14400
            self.calls = []
            self.error = None

        def call(self, path, payload=None, token=None):
            self.calls.append((path, payload, token))
            if path == "auth/token/lookup-self":
                if self.error and token == old:
                    raise broker.ApiError(self.error)
                return {"data": {"policies": self.policies, "identity_policies": self.identity_policies,
                                 "ttl": self.ttl if token == old else self.new_ttl,
                                 "explicit_max_ttl": self.maximum}}
            if path.endswith("/login"):
                assert token is None and payload == {"role_id": config["role_id"], "secret_id": config["secret_id"]}
                return {"auth": {"client_token": fresh, "policies": self.policies}}
            if path == "auth/token/revoke-self":
                return {}
            raise AssertionError("Unexpected endpoint")

    return SimpleNamespace(module=broker, config=config, api=FakeAPI(), old=old, fresh=fresh, runtime=tmp_path)


def run_flow(f, **kwargs):
    events = []
    result = f.module.tick(f.config, f.api, runtime=f.runtime,
                           restart=kwargs.pop("restart", lambda: events.append("restart") or "active"),
                           ready=kwargs.pop("ready", lambda ca: events.append("ready")), **kwargs)
    return result, events


def test_first_login_installs_then_reloads_and_reports_no_values(flow):
    result, events = run_flow(flow)
    assert events == ["restart", "ready"]
    assert result["rotated"] and result["api_reloaded"]
    assert (flow.runtime / "svc-app.token").read_text().strip() == flow.fresh
    serialized = json.dumps(result)
    assert all(value not in serialized for value in (flow.fresh, flow.config["secret_id"], flow.config["role_id"]))
    assert not result["root_material_used"] and not result["database_accessed"]


def test_healthy_token_does_not_rotate_or_restart_again(flow):
    run_flow(flow)
    result, events = run_flow(flow)
    assert not result["rotated"] and not result["api_reloaded"] and not events
    assert sum(path.endswith("/login") for path, _, _ in flow.api.calls) == 1


@pytest.mark.parametrize("remaining", [1, 3599, 3600])
def test_refreshes_before_expiry_and_revokes_previous_after_reload(flow, remaining):
    (flow.runtime / "svc-app.token").write_text(flow.old + "\n")
    flow.api.ttl = remaining
    result, events = run_flow(flow)
    assert result["rotated"] and events == ["restart", "ready"]
    assert flow.api.calls[-1] == ("auth/token/revoke-self", {}, flow.old)


def test_rejected_old_token_recovers_with_approle(flow):
    (flow.runtime / "svc-app.token").write_text(flow.old + "\n")
    flow.api.error = 403
    result, _ = run_flow(flow)
    assert result["rotated"] and result["remaining_ttl_seconds"] == 14400


@pytest.mark.parametrize("status", [0, 500, 503])
def test_outage_preserves_existing_token_and_does_not_restart(flow, status):
    sink = flow.runtime / "svc-app.token"
    sink.write_text(flow.old + "\n")
    flow.api.error = status or -1
    with pytest.raises(flow.module.ApiError):
        run_flow(flow)
    assert sink.read_text().strip() == flow.old
    assert not any(path.endswith("/login") for path, _, _ in flow.api.calls)


@pytest.mark.parametrize("policies,identity_policies,maximum,ttl", [
    (["root"], [], 14400, 14400), (["svc-app", "default"], [], 14400, 14400),
    (["svc-app"], ["key-operator"], 14400, 14400), (["svc-app"], [], 86400, 14400),
    (["svc-app"], [], 14400, float("nan")), (["svc-app"], [], 14400, 0),
])
def test_wrong_policy_or_lifetime_never_installed(flow, policies, identity_policies, maximum, ttl):
    flow.api.policies, flow.api.identity_policies = policies, identity_policies
    flow.api.maximum, flow.api.new_ttl = maximum, ttl
    with pytest.raises(flow.module.RefreshError):
        run_flow(flow)
    assert not (flow.runtime / "svc-app.token").exists()


def test_short_new_token_rejected(flow):
    flow.api.new_ttl = 3700
    with pytest.raises(flow.module.RefreshError):
        run_flow(flow)
    assert not (flow.runtime / "svc-app.token").exists()


def test_intentional_maintenance_is_not_started(flow):
    result, events = run_flow(flow, restart=lambda: "inactive_preserved")
    assert result["service"] == "inactive_preserved" and not result["api_reloaded"]
    assert not events and (flow.runtime / "svc-app.token").exists()


def test_restart_failure_is_retried_without_minting_another_token(flow):
    def fail():
        raise RuntimeError("invented restart failure")
    with pytest.raises(RuntimeError):
        run_flow(flow, restart=fail)
    result, events = run_flow(flow)
    assert events == ["restart", "ready"] and not result["rotated"]
    assert sum(path.endswith("/login") for path, _, _ in flow.api.calls) == 1


def test_readiness_failure_is_retried_and_old_token_not_revoked(flow):
    (flow.runtime / "svc-app.token").write_text(flow.old + "\n")
    flow.api.ttl = 10
    def fail(ca):
        raise flow.module.RefreshError("api_not_ready")
    with pytest.raises(flow.module.RefreshError):
        run_flow(flow, ready=fail)
    assert not any(path == "auth/token/revoke-self" for path, _, _ in flow.api.calls)
    result, events = run_flow(flow)
    assert result["api_reloaded"] and events == ["restart", "ready"]


@pytest.mark.parametrize("value", ["", " ", "a\nb", "a\tb", "\u2603", "x" * 4097, None])
def test_rejects_malformed_tokens(broker, value):
    with pytest.raises(broker.RefreshError):
        broker.token_value(value)


def test_api_refuses_http_remote_and_redirects(broker):
    for address in ("http://127.0.0.1:8200", "https://example.invalid:8200", "https://127.0.0.1:8200/else",
                    "https://user@127.0.0.1:8200", "https://127.0.0.1:8201"):
        with pytest.raises(broker.RefreshError):
            broker.API(address, "not-read")
    assert broker.NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.invalid") is None


def test_atomic_write_refuses_symlink(broker, tmp_path):
    target, link = tmp_path / "target", tmp_path / "link"
    target.write_text("unchanged")
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("Windows symlink privilege unavailable")
    with pytest.raises(broker.RefreshError):
        broker.private_write(link, "changed")
    assert target.read_text() == "unchanged"


def test_private_read_refuses_writable_or_wrong_owner(broker, tmp_path, monkeypatch):
    path = tmp_path / "private"
    path.write_text("not-a-real-credential")
    original = os.fstat
    for owner, mode in ((1234, 0o600), (0, 0o644)):
        def info(fd):
            current = original(fd)
            return SimpleNamespace(st_mode=stat.S_IFREG | mode, st_uid=owner, st_gid=0, st_size=current.st_size)
        with monkeypatch.context() as patch:
            patch.setattr(broker.os, "fstat", info)
            with pytest.raises(broker.RefreshError):
                broker.private_read(path)


def test_existing_role_with_extra_privileges_refused(broker):
    assert broker.role_matches(dict(broker.ROLE_CONFIG))
    assert not broker.role_matches({**broker.ROLE_CONFIG, "token_policies": ["svc-app", "root"]})
    assert not broker.role_matches({**broker.ROLE_CONFIG, "token_explicit_max_ttl": 0})


def test_runtime_unit_has_no_operator_material_and_timer_is_bounded():
    unit = (APP / "deploy/dpr-token-refresh.service").read_text()
    assert "ExecStart=/usr/bin/python3 -I /usr/local/lib/dpr-service-app/token_refresh.py tick" in unit
    assert "InaccessiblePaths=" in unit and "module-a/openbao" in unit
    assert "OnUnitInactiveSec=5min" in (APP / "deploy/dpr-token-refresh.timer").read_text()
    assert "restart dpr-web" not in (APP / "deploy/token_refresh.py").read_text()


def test_runtime_launcher_propagates_only_token_path_to_api():
    script = (APP / "scripts/run_runtime.sh").read_text()
    assert 'DPR_APP_TOKEN_FILE="${DPR_APP_TOKEN_FILE:-}"' in script
    assert "unset DPR_APP_TOKEN_FILE" in script


def test_sink_missing_fails_without_static_fallback(monkeypatch):
    source = load(APP / "backend/service_app/token_source.py", "token_sink_source")
    monkeypatch.setenv("OPENBAO_TOKEN", secrets.token_urlsafe(32))
    monkeypatch.setenv("DPR_APP_TOKEN_FILE", "/run/dpr-service-app/svc-app.token")
    def missing(*args, **kwargs):
        raise FileNotFoundError()
    monkeypatch.setattr(source.os, "open", missing)
    with pytest.raises(FileNotFoundError):
        source.load_runtime_token()


def test_sink_cannot_redirect_to_other_private_file(monkeypatch):
    source = load(APP / "backend/service_app/token_source.py", "token_sink_bad_path")
    monkeypatch.setenv("DPR_APP_TOKEN_FILE", "/tmp/other-token")
    with pytest.raises(ValueError):
        source.load_runtime_token()


def test_manual_runtime_unchanged_when_sink_not_enabled(monkeypatch):
    source = load(APP / "backend/service_app/token_source.py", "token_sink_disabled")
    token = secrets.token_urlsafe(32)
    monkeypatch.delenv("DPR_APP_TOKEN_FILE", raising=False)
    monkeypatch.setenv("OPENBAO_TOKEN", token)
    source.load_runtime_token()
    assert os.environ["OPENBAO_TOKEN"] == token


def test_bootstrap_refuses_foreign_auth_mount(broker, tmp_path):
    class FakeAPI:
        def call(self, path, payload=None, token=None):
            assert path == "sys/auth"
            return {"data": {broker.MOUNT + "/": {"type": "approle", "description": "other owner"}}}
    with pytest.raises(broker.RefreshError, match="auth_mount_not_owned"):
        broker.provision(FakeAPI(), secrets.token_urlsafe(32), address="test", ca="test",
                         gid=1000, destination=tmp_path / "unused")


def test_restart_preserves_inactive_and_never_targets_other_units(broker, monkeypatch):
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout=b"inactive\n")
    monkeypatch.setattr(broker.subprocess, "run", run)
    assert broker.restart_api() == "inactive_preserved"
    assert calls == [["/usr/bin/systemctl", "is-active", "dpr-api.service"]]


def test_restart_failed_api_is_recoverable(broker, monkeypatch):
    calls = []
    monkeypatch.setattr(broker.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=b"failed\n"))
    def execute(arguments):
        calls.append(arguments)
        return "active" if "is-active" in arguments else ""
    monkeypatch.setattr(broker, "command", execute)
    assert broker.restart_api() == "active"
    assert calls == [["/usr/bin/systemctl", "restart", "dpr-api.service"],
                     ["/usr/bin/systemctl", "is-active", "dpr-api.service"]]


def test_cli_error_never_echoes_exception_or_credentials(broker, monkeypatch, capsys):
    secret = secrets.token_urlsafe(32)
    monkeypatch.setattr(broker.os, "geteuid", lambda: 0, raising=False)
    def fail(*args, **kwargs):
        raise ValueError(secret)
    monkeypatch.setattr(broker, "private_read", fail)
    assert broker.main(["tick"]) == 1
    output = capsys.readouterr().out
    assert secret not in output and json.loads(output)["passed"] is False


def test_release_archive_is_only_allowlisted_runtime_files(broker):
    builder = load(APP / "scripts/build_token_refresh_release.py", "test_token_release")
    assert len(builder.FILES) == 8
    assert all(name.startswith("app/") for name in builder.FILES)
    assert not any(word in name for name in builder.FILES for word in (".env", "private", "02_data", "account"))
    installer = (APP / "deploy/install_token_refresh.sh").read_text()
    assert "sha256" in installer and "Release checksum mismatch" in installer
    assert "docker compose" not in installer and "golden_reset" not in installer
