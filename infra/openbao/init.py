"""Operator-invoked init/unseal/configure/issue/revoke; never auto-unseal on startup."""

import argparse
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import sys
import uuid
import warnings

from infra.openbao.api import BaoAPI, BaoError, from_environment
from infra.security import external_directory, secure_directory


POLICIES = ("svc-app", "svc-migration", "svc-verify", "key-operator")
KEYS = {"pii-kek": "aes256-gcm96", "finance-kek": "aes256-gcm96", "search-hmac": "hmac"}


def save_response(path: Path, operation) -> dict:
    # Reserve storage before an irreversible API call. Interrupted/empty files are
    # retained to signal that an operator must investigate, never silently retry init.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        result = operation()
        json.dump(result, stream)
        stream.flush()
        os.fsync(stream.fileno())
    return result


def initialize(api: BaoAPI, directory: Path) -> None:
    if api.request("/sys/init")["initialized"]:
        raise ValueError("OpenBao already initialized; recovery material will not be overwritten")
    destination = secure_directory(directory / "openbao") / "init-material.json"
    save_response(destination, lambda: api.request("/sys/init", {"secret_shares": 3, "secret_threshold": 2}))


def unseal(api: BaoAPI, key: str) -> dict:
    if not key:
        raise ValueError("An unseal share is required")
    return api.request("/sys/unseal", {"key": key})


def read_unseal_share() -> str:
    if not sys.stdin.isatty():
        raise ValueError("Unseal requires an interactive terminal with hidden input")
    with warnings.catch_warnings():
        # getpass must never fall back to echoed stdin on a terminal without no-echo.
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            return getpass.getpass("Unseal share (hidden; one custodian per invocation): ")
        except getpass.GetPassWarning:
            raise ValueError("Hidden input unavailable; unseal aborted") from None


def configure(api: BaoAPI, token: str) -> None:
    if api.request("/sys/seal-status")["sealed"]:
        raise ValueError("Unseal manually before configuring Transit")
    mounts = api.request("/sys/mounts", token=token)["data"]
    if "transit/" not in mounts:
        api.request("/sys/mounts/transit", {"type": "transit"}, token=token)
    elif mounts["transit/"]["type"] != "transit":
        raise ValueError("The transit mount is occupied by another engine")
    api.request("/transit/config/keys", {"disable_upsert": True}, token=token)
    for name, key_type in KEYS.items():
        try:
            key = api.request(f"/transit/keys/{name}", token=token)["data"]
        except BaoError as error:
            if error.status != 404:
                raise
            api.request(f"/transit/keys/{name}", {
                "type": key_type, "derived": False, "exportable": False,
                "allow_plaintext_backup": False,
                **({"key_size": 32} if key_type == "hmac" else {}),
            }, token=token)
            key = api.request(f"/transit/keys/{name}", token=token)["data"]
        if (key["type"] != key_type or key["derived"] or key["exportable"]
                or key["allow_plaintext_backup"] or key["deletion_allowed"]):
            raise ValueError("Existing Transit key has incompatible or unsafe settings")
    for name in POLICIES:
        policy = (Path(__file__).parent / "policies" / f"{name}.hcl").read_text(encoding="utf-8")
        api.request(f"/sys/policies/acl/{name}", {"policy": policy}, token=token)


def issue_tokens(api: BaoAPI, token: str, directory: Path, ttl: int = 3600) -> None:
    if not 60 <= ttl <= 14400:
        raise ValueError("Token TTL must be 60..14400 seconds")
    destination = secure_directory(directory / "openbao" / "tokens")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    for name in POLICIES:
        save_response(destination / f"{name}-{stamp}.json", lambda name=name: api.request(
            "/auth/token/create-orphan", {
                "policies": [name], "no_default_policy": True, "renewable": False,
                "ttl": f"{ttl}s", "explicit_max_ttl": f"{ttl}s",
                "display_name": f"dpr-{name}",
            }, token=token,
        ))


def revoke_migration(api: BaoAPI, token: str) -> None:
    identity = api.request("/auth/token/lookup-self", token=token)["data"]
    if set(identity["policies"]) != {"svc-migration"}:
        raise ValueError("Expected a token with only svc-migration policy")
    api.request("/auth/token/revoke-self", {}, token=token)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "unseal", "configure", "issue", "revoke-migration", "status"))
    parser.add_argument("--ttl-seconds", type=int, default=3600)
    args = parser.parse_args()
    try:
        api = from_environment()
        if args.command == "status":
            state = api.request("/sys/seal-status")
            print(json.dumps({k: state[k] for k in ("initialized", "sealed", "version")}))
        elif args.command == "init":
            directory = secure_directory(external_directory(os.environ.get("DPR_SECRETS_DIR")))
            print("WARNING: unseal shares and root token will be saved together OUTSIDE the repository.")
            print("Separate the shares between custodians and move the root token to offline custody.")
            initialize(api, directory)
            print("Initialization saved to external openbao/init-material.json; server remains sealed.")
        elif args.command == "unseal":
            state = unseal(api, read_unseal_share())
            print(json.dumps({"sealed": state["sealed"], "progress": state.get("progress", 0)}))
        elif args.command == "revoke-migration":
            revoke_migration(api, os.environ["OPENBAO_TOKEN"])
            print("Migration token revoked.")
        else:
            token = os.environ["OPENBAO_TOKEN"]
            directory = secure_directory(external_directory(os.environ.get("DPR_SECRETS_DIR")))
            if args.command == "configure":
                configure(api, token)
                print("Transit keys and four policies configured; root token is only for administration.")
            else:
                issue_tokens(api, token, directory, args.ttl_seconds)
                print("Four non-renewable policy tokens saved outside the repository (no default/root policy).")
    except (BaoError, ValueError, RuntimeError, OSError, KeyError):
        raise SystemExit("OpenBao operation failed; check state, verified TLS, environment and external storage. No response data shown.") from None


if __name__ == "__main__":
    main()
