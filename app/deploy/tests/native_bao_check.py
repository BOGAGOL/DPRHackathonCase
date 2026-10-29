"""Opt-in disposable Linux/OpenBao 2.5.5 TLS integration; never run on the VM.

The container has no published ports, no team secrets, and an empty file backend.
Systemd restart/readiness callbacks are test doubles, explicitly reported as such.
"""
import importlib.util
import json
import os
from pathlib import Path
import secrets
import time

LAST_PATH = "not-started"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    broker = load("/tmp/token_refresh.py", "native_broker")
    source = load("/tmp/token_source.py", "native_source")
    class TraceAPI(broker.API):
        def call(self, path, payload=None, token=None):
            global LAST_PATH
            LAST_PATH = path
            return super().call(path, payload, token)
    api = TraceAPI("https://127.0.0.1:8200", "/tmp/tls/ca.crt")
    for _ in range(30):
        try:
            if api.call("sys/init").get("initialized") is False:
                break
        except broker.ApiError:
            time.sleep(1)
    initialized = api.call("sys/init", {"secret_shares": 1, "secret_threshold": 1})
    api.call("sys/unseal", {"key": initialized["keys"][0]})
    bootstrap = initialized["root_token"]
    api.call("sys/policies/acl/svc-app", {"policy": Path("/tmp/svc-app.hcl").read_text()}, bootstrap)
    root = Path("/tmp/broker-lab")
    root.mkdir(mode=0o700)
    config_file = root / "config.json"
    args = dict(address=api.address, ca="/tmp/tls/ca.crt", gid=1000, destination=config_file)
    checks = {}
    checks["configure_approle"] = broker.provision(api, bootstrap, **args)["passed"]
    config = json.loads(broker.private_read(config_file))
    checks["config_is_root_only"] = config_file.stat().st_mode & 0o777 == 0o600
    checks["idempotent_setup"] = broker.provision(api, bootstrap, **args)["existing_preserved"]
    runtime = Path("/run/dpr-service-app")
    runtime.mkdir(mode=0o750)
    os.chown(runtime, 0, 1000)
    reloads = []
    def tick(force=False, cfg=config):
        return broker.tick(cfg, api, runtime=runtime, force=force,
                           restart=lambda: reloads.append(True) or "active", ready=lambda ca: None)
    checks["first_automatic_login"] = tick()["rotated"]
    first = broker.read_token(runtime / "svc-app.token", 1000)
    checks["token_policy_and_four_hour_cap"] = 13000 < broker.identity(api, first) <= 14400
    try:
        api.call("sys/auth", token=first)
    except broker.ApiError as error:
        checks["application_cannot_manage_auth"] = error.status == 403
    checks["healthy_token_no_restart"] = not tick()["api_reloaded"] and len(reloads) == 1
    api.call("auth/token/revoke-self", {}, first)
    checks["rejected_token_automatic_recovery"] = tick()["rotated"]
    second = broker.read_token(runtime / "svc-app.token", 1000)
    checks["fresh_token_after_rejection"] = second != first
    checks["force_rotation"] = tick(force=True)["rotated"]
    try:
        broker.identity(api, second)
    except broker.ApiError as error:
        checks["previous_token_revoked_after_reload"] = error.status == 403
    installed = broker.read_token(runtime / "svc-app.token", 1000)
    os.environ["DPR_APP_TOKEN_FILE"] = str(runtime / "svc-app.token")
    saved_getegid = source.os.getegid
    source.os.getegid = lambda: 1000
    source.load_runtime_token()
    checks["startup_reads_new_sink"] = os.environ["OPENBAO_TOKEN"] == installed
    source.os.getegid = saved_getegid
    try:
        tick(force=True, cfg={**config, "secret_id": secrets.token_urlsafe(32)})
    except broker.ApiError:
        checks["bad_credential_keeps_last_token"] = broker.read_token(runtime / "svc-app.token", 1000) == installed
    sink = runtime / "svc-app.token"
    sink.chmod(0o644)
    try:
        broker.read_token(sink, 1000)
    except broker.RefreshError:
        checks["publicly_readable_sink_rejected"] = True
    sink.chmod(0o640)
    try:
        broker.API(api.address, "/tmp/tls/wrong-ca.crt").call("sys/init")
    except broker.ApiError:
        checks["wrong_ca_rejected"] = True
    report = {"passed": len(checks) == 15 and all(checks.values()), "checks": checks,
              "openbao_version": "2.5.5", "transport": "verified HTTPS, private disposable container",
              "systemd_callbacks": "test doubles; actual VM service activation NOT TESTED",
              "team_database_or_vm_accessed": False, "credential_values_in_report": False}
    Path("/tmp/native-token-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"passed": False, "error_class": type(error).__name__,
                          "http_status": getattr(error, "status", None), "last_path": LAST_PATH,
                          "details": "withheld"}))
        raise SystemExit(1)
