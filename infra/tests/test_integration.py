"""Opt-in real containers. Only fresh random projects/volumes are created/deleted."""

import base64
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
from urllib.request import urlopen

import pytest

from infra.openbao.api import BaoAPI, BaoError
from infra.openbao.init import configure, initialize, issue_tokens, revoke_migration, unseal
from infra.openbao.verify import verify, write_evidence
from infra.security import REPO, secure_directory
from infra.tls.make_ca import make_ca


@pytest.mark.skipif(os.environ.get("DPR_INFRA_INTEGRATION") != "1", reason="Set DPR_INFRA_INTEGRATION=1 to start isolated Docker test containers")
def test_real_tls_bootstrap_acl_aad_restart_and_postgres(tmp_path):
    project = "dpr-test-" + secrets.token_hex(5)
    # Random host ports published only on loopback; Docker allocates available ports.
    root = secure_directory(tmp_path / "secrets")
    make_ca(root / "tls")
    env = {**os.environ, "DPR_SECRETS_DIR": str(root), "DPR_OPENBAO_PORT": "0",
           "DPR_POSTGRES_PORT": "0", "DPR_POSTGRES_PASSWORD": secrets.token_urlsafe(32)}
    command = ["docker", "compose", "-p", project, "-f", str(REPO / "infra/compose.yaml"), "--profile", "new-postgres"]
    # The project is unpredictable and checked absent before its resources exist.
    collision = subprocess.run(["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={project}"], capture_output=True, text=True, check=True)
    if collision.stdout.strip():
        pytest.fail("Unexpected existing integration project; refusing to use it", pytrace=False)
    def compose(*args):
        result = subprocess.run(command + list(args), env=env, capture_output=True, text=True)
        if result.returncode:
            # Never echo inspect/config/env/errors that could contain credentials.
            raise RuntimeError("Isolated integration compose command failed (output withheld)")
        return result.stdout
    report = {"schema_version": 1, "passed": False, "scope": "disposable containers; synthetic bytes only"}
    try:
        compose("up", "-d", "openbao", "postgres")
        port = compose("port", "openbao", "8200").strip().rsplit(":", 1)[1]
        address = f"https://127.0.0.1:{port}"
        api = BaoAPI(address, str(root / "tls/ca.crt"))
        deadline = time.monotonic() + 90
        while True:
            try:
                state = api.request("/sys/seal-status")
                break
            except BaoError:
                if time.monotonic() > deadline:
                    raise RuntimeError("Isolated OpenBao did not start") from None
                time.sleep(0.5)
        if state["initialized"]:
            raise RuntimeError("Expected fresh, uninitialized server")
        # Verified server is reachable; system CA alone must reject this lab CA.
        make_ca(root / "wrong-ca")
        wrong_ca = BaoAPI(address, str(root / "wrong-ca/ca.crt"))
        tls_rejected = False
        try:
            wrong_ca.request("/sys/seal-status")
        except BaoError as error:
            tls_rejected = error.status == 0
        http_rejected = False
        try:
            with urlopen(f"http://127.0.0.1:{port}/v1/sys/seal-status", timeout=3) as response:
                http_rejected = response.status != 200
        except OSError:
            http_rejected = True
        initialize(api, root)
        material = json.loads((root / "openbao/init-material.json").read_text())
        root_token = material["root_token"]
        shares = material["keys_base64"]
        first = unseal(api, shares[0])
        second = unseal(api, shares[1])
        threshold_ok = first["sealed"] and not second["sealed"]
        configure(api, root_token)
        configure(api, root_token)  # Reentry must preserve key versions/material.
        issue_tokens(api, root_token, root, 600)
        tokens = {name: json.loads(next((root / "openbao/tokens").glob(f"{name}-*.json")).read_text())["auth"]["client_token"]
                  for name in ("svc-app", "svc-migration", "svc-verify", "key-operator")}
        report = verify(api, tokens)
        report["passed"] = False  # Remaining lifecycle checks must also finish.
        report["scope"] = "disposable containers; synthetic bytes only"
        report["checks"].update({"wrong_ca_rejected": tls_rejected, "http_rejected": http_rejected,
                                 "manual_unseal_threshold": threshold_ok})
        # Exercise all allowed operator operations only in these disposable volumes.
        for key in ("pii-kek", "finance-kek", "search-hmac"):
            api.request(f"/transit/keys/{key}/rotate", {}, token=tokens["key-operator"])
            api.request(f"/transit/keys/{key}/config", {"min_decryption_version": 1, "min_encryption_version": 1}, token=tokens["key-operator"])
            metadata = api.request(f"/transit/keys/{key}", token=tokens["key-operator"])["data"]
            report["checks"][f"operator:rotate_config:{key}"] = metadata["latest_version"] == 2 and not metadata["exportable"]
        # Persisted key/version survive restart; shares must be entered again.
        plain = os.urandom(32)
        ciphertext = api.request("/transit/encrypt/pii-kek", {"plaintext": base64.b64encode(plain).decode()}, token=tokens["svc-app"])["data"]["ciphertext"]
        compose("restart", "openbao")
        # Docker may allocate a different ephemeral host port after restart.
        port = compose("port", "openbao", "8200").strip().rsplit(":", 1)[1]
        api = BaoAPI(f"https://127.0.0.1:{port}", str(root / "tls/ca.crt"))
        for _ in range(60):
            try:
                state = api.request("/sys/seal-status")
                break
            except BaoError:
                time.sleep(0.5)
        else:
            raise RuntimeError("Restarted OpenBao was not reachable")
        report["checks"]["restart_requires_unseal"] = state["sealed"]
        unseal(api, shares[0])
        unseal(api, shares[1])
        decrypted = api.request("/transit/decrypt/pii-kek", {"ciphertext": ciphertext}, token=tokens["svc-app"])["data"]["plaintext"]
        report["checks"]["restart_preserves_key"] = base64.b64decode(decrypted, validate=True) == plain
        revoke_migration(api, tokens["svc-migration"])
        try:
            api.request("/auth/token/lookup-self", token=tokens["svc-migration"])
            report["checks"]["migration_revocation"] = False
        except BaoError as error:
            report["checks"]["migration_revocation"] = error.status == 403
        # Query only the disposable new dpr_lab database, never the existing pg-dpr.
        for _ in range(60):
            readiness = subprocess.run(command + ["exec", "-T", "postgres", "pg_isready", "-U", "dpr_bootstrap", "-d", "dpr_lab"], env=env, capture_output=True)
            if readiness.returncode == 0:
                break
            time.sleep(0.5)
        version = compose("exec", "-T", "postgres", "psql", "-U", "dpr_bootstrap", "-d", "dpr_lab", "-Atc", "SHOW server_version_num").strip()
        report["checks"]["postgres_18"] = 180000 <= int(version) < 190000
        report["postgres_server_version_num"] = int(version)
        # Root revocation must not revoke orphan workload tokens.
        api.request("/auth/token/revoke-self", {}, token=root_token)
        identity = api.request("/auth/token/lookup-self", token=tokens["svc-app"])["data"]
        report["checks"]["root_revocation_preserves_workload"] = identity["policies"] == ["svc-app"]
        report["passed"] = all(report["checks"].values())
        if not report["passed"]:
            failed = [name for name, passed in report["checks"].items() if not passed]
            pytest.fail("Integration checks failed: " + ", ".join(failed), pytrace=False)
    finally:
        write_evidence(report, REPO / "evidence/infra/integration.json")
        # Only this test's fresh random project and volumes, not dpr-infra/pg-dpr.
        compose("down", "--volumes", "--remove-orphans")
