"""Verify AAD and ACLs with four workload tokens; save only non-secret evidence."""

import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from infra.openbao.api import BaoAPI, BaoError, from_environment
from infra.openbao.init import POLICIES
from infra.security import REPO


def rejected(api: BaoAPI, path: str, payload: dict | None, token: str, status: int) -> bool:
    try:
        api.request(path, payload, token=token)
    except BaoError as error:
        return error.status == status
    return False


def probe_associated_data(api: BaoAPI, token: str) -> dict:
    # This only probes wrapping. Production field AEAD/AAD remains local to each DEK.
    plaintext = os.urandom(32)
    aad = base64.b64encode(b"dpr|infra-probe|v1").decode()
    ciphertext = api.request("/transit/encrypt/pii-kek", {
        "plaintext": base64.b64encode(plaintext).decode(), "associated_data": aad,
    }, token=token)["data"]["ciphertext"]
    decrypted = api.request("/transit/decrypt/pii-kek", {
        "ciphertext": ciphertext, "associated_data": aad,
    }, token=token)["data"]["plaintext"]
    return {
        "roundtrip": base64.b64decode(decrypted, validate=True) == plaintext,
        "wrong_aad_rejected": rejected(api, "/transit/decrypt/pii-kek", {
            "ciphertext": ciphertext, "associated_data": base64.b64encode(b"wrong-aad").decode(),
        }, token, 400),
        "missing_aad_rejected": rejected(api, "/transit/decrypt/pii-kek", {"ciphertext": ciphertext}, token, 400),
    }


def verify(api: BaoAPI, tokens: dict[str, str]) -> dict:
    state = api.request("/sys/seal-status")
    report = {"schema_version": 1, "version": state["version"], "tls_verified": True, "checks": {}}
    checks = report["checks"]
    checks["pinned_version"] = state["version"] == "2.5.5"
    for name in POLICIES:
        identity = api.request("/auth/token/lookup-self", token=tokens[name])["data"]
        checks[f"{name}:identity_and_ttl"] = (
            set(identity["policies"]) == {name} and not identity["renewable"]
            and identity["orphan"] and 0 < identity["ttl"] <= 14400
            and 0 < identity["explicit_max_ttl"] <= 14400
        )
    if not all(checks.values()):
        report["passed"] = False
        return report
    # Inspect these ACLs rather than executing an operation that could rotate a
    # key, issue a token, or return key material if a policy has drifted.
    protected_paths = ["auth/token/create", "auth/token/create-orphan",
                       "transit/export/encryption-key/pii-kek",
                       "transit/keys/pii-kek/rotate", "transit/keys/finance-kek/rotate"]
    capabilities = {name: api.request("/sys/capabilities-self", {"paths": protected_paths}, token=tokens[name])["data"]
                    for name in POLICIES}
    app = tokens["svc-app"]
    migration = tokens["svc-migration"]
    operator = tokens["key-operator"]
    report["associated_data"] = probe_associated_data(api, app)
    for name, result in report["associated_data"].items():
        checks[f"associated_data:{name}"] = result
    for key in ("pii-kek", "finance-kek"):
        plain = os.urandom(32)
        wrapped = api.request(f"/transit/encrypt/{key}", {
            "plaintext": base64.b64encode(plain).decode(),
        }, token=migration)["data"]["ciphertext"]
        result = api.request(f"/transit/decrypt/{key}", {"ciphertext": wrapped}, token=app)["data"]["plaintext"]
        checks[f"{key}:migration_wrap_app_unwrap"] = base64.b64decode(result, validate=True) == plain
        for policy in ("svc-migration", "svc-verify", "key-operator"):
            checks[f"{policy}:deny_decrypt:{key}"] = rejected(
                api, f"/transit/decrypt/{key}", {"ciphertext": wrapped}, tokens[policy], 403,
            )
        for kind in ("wrapped", "plaintext"):
            data = api.request(f"/transit/datakey/{kind}/{key}", {"bits": 256}, token=migration)["data"]
            checks[f"{key}:migration_datakey:{kind}"] = data["ciphertext"].startswith("vault:v") and (
                len(base64.b64decode(data["plaintext"], validate=True)) == 32 if kind == "plaintext" else "plaintext" not in data
            )
        for policy in ("svc-app", "svc-migration", "svc-verify"):
            checks[f"{policy}:deny_rotate:{key}"] = capabilities[policy].get(f"transit/keys/{key}/rotate") == ["deny"]
        checks[f"operator:deny_export_config:{key}"] = rejected(
            api, f"/transit/keys/{key}/config", {"exportable": False}, operator, 403,
        )
        checks[f"operator:deny_backup_config:{key}"] = rejected(
            api, f"/transit/keys/{key}/config", {"allow_plaintext_backup": False}, operator, 403,
        )
        checks[f"operator:deny_delete_config:{key}"] = rejected(
            api, f"/transit/keys/{key}/config", {"deletion_allowed": False}, operator, 403,
        )
        rewrapped = api.request(f"/transit/rewrap/{key}", {"ciphertext": wrapped}, token=operator)["data"]["ciphertext"]
        decrypted = api.request(f"/transit/decrypt/{key}", {"ciphertext": rewrapped}, token=app)["data"]["plaintext"]
        checks[f"operator:rewrap:{key}"] = base64.b64decode(decrypted, validate=True) == plain
    hmac_input = {"input": base64.b64encode(b"bidx|v1|email|synthetic@example.test").decode(), "algorithm": "sha2-256"}
    hmac_app = api.request("/transit/hmac/search-hmac", hmac_input, token=app)["data"]["hmac"]
    hmac_migration = api.request("/transit/hmac/search-hmac", hmac_input, token=migration)["data"]["hmac"]
    checks["hmac:shared_result"] = (
        hmac_app == hmac_migration and hmac_app.startswith("vault:v")
        and len(base64.b64decode(hmac_app.rsplit(":", 1)[-1], validate=True)) == 32
    )
    for policy in POLICIES:
        checks[f"{policy}:deny_issue_token"] = all(capabilities[policy].get(path) == ["deny"]
            for path in ("auth/token/create", "auth/token/create-orphan"))
        checks[f"{policy}:deny_key_export"] = capabilities[policy].get("transit/export/encryption-key/pii-kek") == ["deny"]
    for policy in ("svc-verify", "key-operator"):
        token = tokens[policy]
        checks[f"{policy}:deny_encrypt"] = rejected(api, "/transit/encrypt/pii-kek", {"plaintext": base64.b64encode(os.urandom(32)).decode()}, token, 403)
        checks[f"{policy}:deny_hmac"] = rejected(api, "/transit/hmac/search-hmac", hmac_input, token, 403)
        checks[f"{policy}:deny_datakey"] = rejected(api, "/transit/datakey/plaintext/pii-kek", {}, token, 403)
    report["passed"] = all(checks.values())
    return report


def write_evidence(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output = {**report, "checked_at_utc": datetime.now(timezone.utc).isoformat()}
    path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    report = {"schema_version": 1, "passed": False}
    try:
        tokens = {name: os.environ["OPENBAO_" + name.upper().replace("-", "_") + "_TOKEN"] for name in POLICIES}
        report = verify(from_environment(), tokens)
    except (BaoError, ValueError, OSError, KeyError) as error:
        report["error"] = "verification_unavailable"
        if isinstance(error, BaoError):
            report["http_status"] = error.status
    write_evidence(report, REPO / "evidence/infra/openbao.json")
    print("OpenBao verification: " + ("PASS" if report["passed"] else "FAIL") + "; evidence/infra/openbao.json")
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
