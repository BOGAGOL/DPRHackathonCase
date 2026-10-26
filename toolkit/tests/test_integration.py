"""Real OpenBao 2.5.5, TLS and workload ACLs in a disposable project; no database."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
from uuid import uuid4

import pytest

from dprcrypto import (BlindIndexer, DecryptionError, KeyManager, OpenBaoClient,
                       OpenBaoError, decrypt, encrypt)
from infra.openbao.api import BaoAPI, BaoError
from infra.openbao.init import configure, initialize, issue_tokens, unseal
from infra.security import secure_directory
from infra.tls.make_ca import make_ca


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(os.environ.get("DPR_CRYPTO_INTEGRATION") != "1", reason="Set DPR_CRYPTO_INTEGRATION=1 for a disposable TLS OpenBao integration test")
def test_workload_envelope_page_batch_acl_cache_rotation_and_outage(tmp_path, monkeypatch, caplog):
    project = "dpr-crypto-test-" + secrets.token_hex(5)
    directory = secure_directory(tmp_path / "secrets")
    make_ca(directory / "tls")
    env = {**os.environ, "DPR_SECRETS_DIR": str(directory), "DPR_OPENBAO_PORT": "0"}
    command = ["docker", "compose", "-p", project, "-f", str(ROOT / "infra/compose.yaml")]
    existing = subprocess.run(["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={project}"], capture_output=True, text=True, check=True)
    if existing.stdout.strip():
        pytest.fail("Unexpected existing integration resources; refusing to continue", pytrace=False)
    def compose(*args):
        result = subprocess.run(command + list(args), env=env, capture_output=True, text=True, timeout=180)
        if result.returncode:
            raise RuntimeError("Disposable compose command failed; output withheld")
        return result.stdout
    report = {"schema_version": 1, "passed": False, "checks": {}, "scope": "synthetic records; disposable TLS OpenBao; no database"}
    checks = report["checks"]
    try:
        compose("up", "-d", "openbao")
        port = compose("port", "openbao", "8200").strip().rsplit(":", 1)[1]
        address = f"https://127.0.0.1:{port}"
        ca = str(directory / "tls/ca.crt")
        api = BaoAPI(address, ca)
        for _ in range(60):
            try:
                state = api.request("/sys/seal-status")
                break
            except BaoError:
                time.sleep(0.5)
        else:
            raise RuntimeError("Disposable OpenBao did not become reachable")
        if state["initialized"]:
            raise RuntimeError("Expected a fresh isolated server")
        report["openbao_version"] = state["version"]
        initialize(api, directory)
        material = json.loads((directory / "openbao/init-material.json").read_text())
        for share in material["keys_base64"][:2]:
            unseal(api, share)
        configure(api, material["root_token"])
        issue_tokens(api, material["root_token"], directory, 600)
        tokens = {name: json.loads(next((directory / "openbao/tokens").glob(f"{name}-*.json")).read_text())["auth"]["client_token"]
                  for name in ("svc-app", "svc-migration", "svc-verify", "key-operator")}
        monkeypatch.setenv("OPENBAO_ADDR", address)
        monkeypatch.setenv("OPENBAO_CACERT", ca)
        monkeypatch.setenv("OPENBAO_TOKEN", tokens["svc-app"])
        with OpenBaoClient() as client, KeyManager(client) as manager:
            paths = []
            client._http.event_hooks["request"].append(lambda request: paths.append(request.url.path))
            identities = [uuid4() for _ in range(50)]
            records = [manager.create_record_keys() for _ in identities]
            plain_keys = [key for record in records for key in (record.pii.dek, record.finance.dek)]
            checks["unique_per_record_domain_deks"] = len(set(plain_keys)) == 100
            before = len(paths)
            pii = manager.unwrap_many("pii-kek", [record.pii.wrapped for record in records])
            checks["page_50_one_pii_batch"] = paths[before:] == ["/v1/transit/decrypt/pii-kek"]
            before = len(paths)
            finance = manager.unwrap_many("finance-kek", [record.finance.wrapped for record in records])
            checks["page_50_one_finance_batch"] = paths[before:] == ["/v1/transit/decrypt/finance-kek"]
            checks["batch_order_and_keys"] = all(pii[i] == record.pii.dek and finance[i] == record.finance.dek for i, record in enumerate(records))
            before = len(paths)
            manager.unwrap_many("pii-kek", [record.pii.wrapped for record in records])
            checks["page_cache_no_extra_request"] = len(paths) == before
            blobs = [encrypt(f"Anggota Uji {i}", pii[i], column="nama", anggota_id=identity) for i, identity in enumerate(identities)]
            checks["field_roundtrip_50_records"] = all(decrypt(blob, pii[i], column="nama", anggota_id=identities[i]) == f"Anggota Uji {i}" for i, blob in enumerate(blobs))
            for name, dek, identity, column, blob in (
                ("record_swap_rejected", pii[0], identities[1], "nama", blobs[0]),
                ("column_swap_rejected", pii[0], identities[0], "rekening", blobs[0]),
                ("domain_key_rejected", finance[0], identities[0], "nama", blobs[0]),
                ("bit_tamper_rejected", pii[0], identities[0], "nama", blobs[0][:-1] + bytes([blobs[0][-1] ^ 1])),
            ):
                try:
                    decrypt(blob, dek, column=column, anggota_id=identity)
                    checks[name] = False
                except DecryptionError:
                    checks[name] = True
            # A mixed valid/tampered real Transit batch returns no partial page/cache.
            from base64 import b64decode, b64encode
            raw = bytearray(b64decode(records[1].pii.wrapped.split(":", 2)[2]))
            raw[-1] ^= 1
            corrupt = "vault:v1:" + b64encode(raw).decode()
            manager.clear()
            try:
                manager.unwrap_many("pii-kek", [records[0].pii.wrapped, corrupt])
                checks["mixed_batch_fail_closed"] = False
            except OpenBaoError:
                checks["mixed_batch_fail_closed"] = not manager._cache
            # HMAC uses a version explicitly; rotation must preserve existing lookups.
            indexer = BlindIndexer(client)
            digest = indexer.digest("email", "  UJI@EXAMPLE.TEST  ")
            checks["hmac_normalization"] = digest == indexer.digest("email", "uji@example.test") and len(digest) == 32
            api.request("/transit/keys/search-hmac/rotate", {}, token=tokens["key-operator"])
            checks["hmac_pinned_after_rotation"] = digest == indexer.digest("email", "uji@example.test")
            checks["hmac_new_version_distinct"] = digest != BlindIndexer(client, key_version=2).digest("email", "uji@example.test")
            api.request("/transit/keys/pii-kek/rotate", {}, token=tokens["key-operator"])
            newer = manager.new_dek("pii-kek")
            checks["new_wrap_uses_rotated_kek"] = newer.wrapped.startswith("vault:v2:")
            checks["old_wrap_still_unwraps"] = manager.unwrap("pii-kek", records[0].pii.wrapped) == records[0].pii.dek
            # Warm cache, change token to a role without decrypt: must not reuse DEKs.
            monkeypatch.setenv("OPENBAO_TOKEN", tokens["svc-verify"])
            try:
                manager.unwrap("pii-kek", records[0].pii.wrapped)
                checks["token_change_cannot_reuse_cache"] = False
            except OpenBaoError:
                checks["token_change_cannot_reuse_cache"] = not manager._cache
            monkeypatch.setenv("OPENBAO_TOKEN", tokens["svc-migration"])
            migration_key = manager.new_dek("pii-kek")
            checks["migration_local_dek_and_wrap"] = len(migration_key.dek) == 32
            try:
                manager.unwrap("pii-kek", migration_key.wrapped)
                checks["migration_no_decrypt"] = False
            except OpenBaoError:
                checks["migration_no_decrypt"] = True
            checks["migration_hmac_matches_app"] = digest == indexer.digest("email", "uji@example.test")
            monkeypatch.setenv("OPENBAO_TOKEN", material["root_token"])
            try:
                manager.unwrap("pii-kek", records[0].pii.wrapped)
                checks["root_token_refused"] = False
            except OpenBaoError:
                checks["root_token_refused"] = True
            monkeypatch.setenv("OPENBAO_TOKEN", tokens["svc-app"])
            manager.clear()
            # The workload client must reject an unrelated CA with real transport.
            make_ca(directory / "unrelated")
            monkeypatch.setenv("OPENBAO_CACERT", str(directory / "unrelated/ca.crt"))
            with OpenBaoClient() as wrong_ca:
                try:
                    wrong_ca.authorization_scope()
                    checks["tls_wrong_ca_rejected"] = False
                except OpenBaoError:
                    checks["tls_wrong_ca_rejected"] = True
            monkeypatch.setenv("OPENBAO_CACERT", ca)
            manager.unwrap("pii-kek", records[0].pii.wrapped)
            manager.clear()
            compose("stop", "openbao")
            try:
                manager.unwrap("pii-kek", records[0].pii.wrapped)
                checks["uncached_outage_fail_closed"] = False
            except OpenBaoError:
                checks["uncached_outage_fail_closed"] = not manager._cache
            checks["no_workload_secrets_in_logs"] = all(token not in caplog.text for token in tokens.values()) and all(key.hex() not in caplog.text for key in plain_keys)
        report["passed"] = all(checks.values())
        if not report["passed"]:
            pytest.fail("Toolkit integration checks failed: " + ", ".join(name for name, ok in checks.items() if not ok), pytrace=False)
    finally:
        report["checked_at_utc"] = datetime.now(timezone.utc).isoformat()
        destination = ROOT / "evidence/crypto/integration.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        compose("down", "--volumes", "--remove-orphans")
