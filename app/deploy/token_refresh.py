"""Root-installed, stdlib-only AppRole broker; no database or cryptographic operations.

Only setup reads operator material. The timer has only a dedicated svc-app AppRole
credential, verifies TLS/policy/TTL, and installs a token before restarting the API.
No token, response body, credential, or exception text is printed.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import secrets
import ssl
import stat
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener

CONFIG = Path("/etc/dpr-service-app/auto-token.json")
RUNTIME = Path("/run/dpr-service-app")
MOUNT = "dpr-service-app"
ROLE = "service-app"
DESCRIPTION = "DPR Service B automated svc-app identity v1"
TTL = 14400
REFRESH_BEFORE = 3600
ROLE_CONFIG = {
    "bind_secret_id": True, "secret_id_ttl": 0, "secret_id_num_uses": 0,
    "token_policies": ["svc-app"], "token_no_default_policy": True,
    "token_ttl": TTL, "token_max_ttl": TTL, "token_explicit_max_ttl": TTL,
    "token_num_uses": 0, "token_period": 0, "token_type": "service",
}


class RefreshError(Exception):
    """A fixed, non-secret error code; never include API response content."""


class ApiError(RefreshError):
    def __init__(self, status=0):
        self.status = status
        super().__init__("openbao_request_failed")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class API:
    def __init__(self, address, ca):
        parsed = urlsplit(address)
        if (parsed.scheme != "https" or parsed.hostname != "127.0.0.1" or parsed.port != 8200
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in ("", "/")):
            raise RefreshError("unexpected_openbao_origin")
        self.address = address.rstrip("/")
        context = ssl.create_default_context(cafile=ca)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context), NoRedirect())

    def call(self, path, payload=None, token=None):
        if path.startswith("/") or ".." in path:
            raise RefreshError("invalid_api_path")
        headers = {"Content-Type": "application/json", "X-Vault-Request": "true"}
        if token:
            headers["X-Vault-Token"] = token
        request = Request(self.address + "/v1/" + path,
                          data=None if payload is None else json.dumps(payload).encode(), headers=headers)
        try:
            with self.opener.open(request, timeout=10) as response:
                content = response.read(65537)
                if len(content) > 65536:
                    raise RefreshError("response_too_large")
                return json.loads(content) if content else {}
        except HTTPError as error:
            status = error.code
            error.close()
            raise ApiError(status) from None
        except (URLError, OSError, ValueError):
            raise ApiError() from None


def private_read(path, *, owner=0, group=None, mode=0o600):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != owner
                or stat.S_IMODE(info.st_mode) != mode or info.st_size > 65536
                or (group is not None and info.st_gid != group)):
            raise RefreshError("unsafe_private_file")
        with os.fdopen(descriptor, "r", encoding="utf-8", closefd=False) as stream:
            return stream.read(65537)
    finally:
        os.close(descriptor)


def private_write(path, content, *, gid=0, mode=0o600):
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise RefreshError("unsafe_destination")
    temporary = path.with_name("." + path.name + "." + secrets.token_hex(8))
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        if hasattr(os, "fchown"):
            os.fchown(descriptor, 0, gid)
        os.fchmod(descriptor, mode) if hasattr(os, "fchmod") else None
        with os.fdopen(descriptor, "w", encoding="utf-8", closefd=False) as stream:
            stream.write(content)
            stream.flush()
            os.fsync(descriptor)
        os.replace(temporary, path)
    finally:
        os.close(descriptor)
        temporary.unlink(missing_ok=True)


def token_value(value):
    if (not isinstance(value, str) or not value or not value.isascii()
            or len(value) > 4096 or any(char.isspace() for char in value)):
        raise RefreshError("invalid_token")
    return value


def identity(api, token):
    data = api.call("auth/token/lookup-self", token=token)["data"]
    ttl, maximum = data["ttl"], data["explicit_max_ttl"]
    if (data.get("policies") != ["svc-app"] or data.get("identity_policies", [])
            or type(ttl) not in (int, float) or type(maximum) not in (int, float)
            or not math.isfinite(ttl) or not math.isfinite(maximum)
            or not 0 < ttl <= maximum <= TTL):
        raise RefreshError("unexpected_token_scope_or_ttl")
    return int(ttl)


def role_matches(data):
    return all(data.get(name) == expected for name, expected in ROLE_CONFIG.items()) and not any(
        data.get(name) for name in ("secret_id_bound_cidrs", "token_bound_cidrs"))


def provision(api, bootstrap, *, address, ca, gid, destination=CONFIG):
    mounts = api.call("sys/auth", token=bootstrap)["data"]
    mount = mounts.get(MOUNT + "/")
    if mount is None:
        api.call("sys/auth/" + MOUNT, {"type": "approle", "description": DESCRIPTION}, bootstrap)
    elif mount.get("type") != "approle" or mount.get("description") != DESCRIPTION:
        raise RefreshError("auth_mount_not_owned_by_service_b")
    # No policy/key changes. The existing reviewed policy must already exist.
    api.call("sys/policies/acl/svc-app", token=bootstrap)
    role_path = "auth/" + MOUNT + "/role/" + ROLE
    try:
        existing = api.call(role_path, token=bootstrap)["data"]
    except ApiError as error:
        if error.status != 404:
            raise
        api.call(role_path, ROLE_CONFIG, bootstrap)
        existing = api.call(role_path, token=bootstrap)["data"]
    if not role_matches(existing):
        raise RefreshError("existing_approle_settings_mismatch")
    if destination.exists() or destination.is_symlink():
        config = json.loads(private_read(destination))
        if (config["address"], config["ca"], config["gid"]) != (address, ca, gid):
            raise RefreshError("existing_broker_config_mismatch")
        return {"passed": True, "action": "setup", "existing_preserved": True}
    role_id = api.call(role_path + "/role-id", token=bootstrap)["data"]["role_id"]
    credential = api.call(role_path + "/secret-id", {}, bootstrap)["data"]
    config = {"version": 1, "address": address, "ca": ca, "gid": gid,
              "role_id": role_id, "secret_id": credential["secret_id"],
              "secret_id_accessor": credential["secret_id_accessor"]}
    try:
        private_write(destination, json.dumps(config) + "\n")
    except Exception:
        api.call(role_path + "/secret-id-accessor/destroy",
                 {"secret_id_accessor": credential["secret_id_accessor"]}, bootstrap)
        raise
    return {"passed": True, "action": "setup", "existing_preserved": False}


def read_token(path, gid):
    try:
        return token_value(private_read(path, group=gid, mode=0o640).removesuffix("\n"))
    except FileNotFoundError:
        return None


def command(arguments):
    return subprocess.run(arguments, check=True, capture_output=True, timeout=70,
                          env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin"}).stdout.decode().strip()


def restart_api():
    state = subprocess.run(["/usr/bin/systemctl", "is-active", "dpr-api.service"],
                           capture_output=True, timeout=10).stdout.decode().strip()
    if state == "inactive":
        return "inactive_preserved"
    if state not in ("active", "failed", "activating"):
        raise RefreshError("api_service_state_unexpected")
    # Inactive maintenance stays inactive. Failed application services may recover.
    command(["/usr/bin/systemctl", "restart", "dpr-api.service"])
    if command(["/usr/bin/systemctl", "is-active", "dpr-api.service"]) != "active":
        raise RefreshError("api_restart_failed")
    return "active"


def wait_ready(ca):
    context = ssl.create_default_context(cafile=ca)
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context), NoRedirect())
    for _ in range(20):
        try:
            with opener.open("https://127.0.0.1:8100/health/ready", timeout=3) as response:
                if response.status == 200 and json.loads(response.read(4096)).get("message") == "ready":
                    return
        except (URLError, HTTPError, OSError, ValueError):
            pass
        time.sleep(1)
    raise RefreshError("api_not_ready")


def tick(config, api, *, runtime=RUNTIME, force=False, restart=restart_api, ready=wait_ready):
    sink, state_path = runtime / "svc-app.token", runtime / "state.json"
    old = read_token(sink, config["gid"])
    ttl, rotated = 0, False
    if old:
        try:
            ttl = identity(api, old)
        except ApiError as error:
            if error.status != 403:
                raise  # Network/TLS/sealed failure: preserve the existing token.
    new = old
    if force or ttl <= REFRESH_BEFORE:
        auth = api.call("auth/" + MOUNT + "/login", {
            "role_id": config["role_id"], "secret_id": config["secret_id"]})["auth"]
        new = token_value(auth["client_token"])
        if auth.get("policies") != ["svc-app"] or auth.get("token_policies", ["svc-app"]) != ["svc-app"]:
            raise RefreshError("login_policy_mismatch")
        ttl = identity(api, new)
        if ttl <= REFRESH_BEFORE + 300:
            raise RefreshError("new_token_lifetime_too_short")
        private_write(sink, new + "\n", gid=config["gid"], mode=0o640)
        rotated = True
    generation = sink.stat().st_mtime_ns
    try:
        previous = json.loads(private_read(state_path))
    except FileNotFoundError:
        previous = {}
    needs_restart = previous.get("applied_generation") != generation
    service = previous.get("service", "unknown")
    if needs_restart:
        service = restart()
        if service == "active":
            ready(config["ca"])
        elif service != "inactive_preserved":
            raise RefreshError("unexpected_restart_result")
    report = {"passed": True, "action": "tick", "rotated": rotated,
              "remaining_ttl_seconds": ttl, "refresh_before_seconds": REFRESH_BEFORE,
              "api_reloaded": needs_restart and service == "active", "service": service,
              "applied_generation": generation, "checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "root_material_used": False, "database_accessed": False,
              "postgres_openbao_restarted": False}
    private_write(state_path, json.dumps(report, indent=2) + "\n")
    if rotated and old and new != old:
        try:
            api.call("auth/token/revoke-self", {}, old)
        except ApiError:
            pass  # Prior token still has a hard maximum of four hours.
    return report


@contextmanager
def exclusive_tick(runtime):
    import fcntl
    descriptor = os.open(runtime / "refresh.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(descriptor)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("setup", "tick", "status"))
    parser.add_argument("--material", type=Path)
    parser.add_argument("--operator-uid", type=int)
    parser.add_argument("--gid", type=int)
    parser.add_argument("--ca")
    parser.add_argument("--address", default="https://127.0.0.1:8200")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not hasattr(os, "geteuid") or os.geteuid() != 0:
            raise RefreshError("run_installed_broker_as_root")
        if args.action == "setup":
            expected = Path("/home/ubuntu/dpr-demo-zhafif/private/module-a/openbao/init-material.json")
            if (args.material != expected or type(args.operator_uid) is not int or args.operator_uid < 1
                    or type(args.gid) is not int or args.gid < 1
                    or args.ca != "/home/ubuntu/dpr-demo-zhafif/private/module-a/tls/ca.crt"):
                raise RefreshError("unexpected_operator_paths_or_identity")
            material = json.loads(private_read(args.material, owner=args.operator_uid))
            report = provision(API(args.address, args.ca), material["root_token"],
                               address=args.address, ca=args.ca, gid=args.gid)
        else:
            config = json.loads(private_read(CONFIG))
            if config.get("version") != 1 or type(config.get("gid")) is not int or config["gid"] < 1:
                raise RefreshError("invalid_broker_configuration")
            if args.action == "status":
                report = json.loads(private_read(RUNTIME / "state.json"))
            else:
                with exclusive_tick(RUNTIME):
                    report = tick(config, API(config["address"], config["ca"]), force=args.force)
        print(json.dumps(report))
        return 0
    except Exception as error:
        allowed = {"unexpected_token_scope_or_ttl", "login_policy_mismatch", "new_token_lifetime_too_short",
                   "existing_approle_settings_mismatch", "auth_mount_not_owned_by_service_b",
                   "api_not_ready", "unsafe_private_file", "run_installed_broker_as_root"}
        code = str(error) if type(error) is RefreshError and str(error) in allowed else "token_refresh_failed_details_withheld"
        print(json.dumps({"passed": False, "action": args.action, "error": code,
                          "http_status": error.status if isinstance(error, ApiError) else None}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
