"""Invented records, disposable PG18 + OpenBao; no organizer data fixtures."""

import json
import hashlib
import io
from contextlib import contextmanager
import os
import secrets
import subprocess
import time

import psycopg
from psycopg import sql
import pytest

from dprcrypto import OpenBaoClient
from infra.openbao.api import BaoAPI, BaoError
from infra.openbao.init import configure, initialize, issue_tokens, unseal
from infra.postgres.enable_tls import ExistingPostgres, TLSUpdateError
from infra.postgres.make_cert import make_certificate
from infra.protected.apply import load_profile, provision
from infra.protected.credentials import ROLES
from infra.security import REPO, secure_directory
from infra.tls.make_ca import make_ca
from migration.model import protect_batch, target_columns
from scripts.backup.crypto import BackupError, canonical, key_id, sign_manifest
from scripts.backup.drills import retention_test, synthetic_member, tamper_test
from scripts.backup.postgres import (Tools, check_roles, check_server, create_database,
    drop_created_database, row_counts)
from scripts.backup.runner import backup, inspect_manifest, restore, smoke_decrypt, source_allowed
from scripts.backup.settings import artifact_store


@pytest.fixture(scope="module")
def laboratory(tmp_path_factory):
    if os.environ.get("DPR_BACKUP_INTEGRATION") != "1":
        pytest.skip("Set DPR_BACKUP_INTEGRATION=1 for disposable TLS PG18/OpenBao backup drills")
    folder = tmp_path_factory.mktemp("backup-lab")
    root = secure_directory(folder/"secrets"); make_ca(root/"tls"); make_certificate(root)
    password = secrets.token_urlsafe(36); project = "dpr-backup-test-"+secrets.token_hex(5)
    environment = {**os.environ, "DPR_SECRETS_DIR": str(root), "DPR_POSTGRES_PASSWORD": password,
        "DPR_POSTGRES_PORT": "0", "DPR_OPENBAO_PORT": "0"}
    command = ["docker", "compose", "-p", project, "-f", str(REPO/"infra/compose.yaml"), "-f", str(REPO/"infra/tests/compose.postgres.yaml")]
    def compose(*args):
        result = subprocess.run(command+list(args), env=environment, capture_output=True, text=True, timeout=180)
        if result.returncode: raise RuntimeError("Disposable backup compose failed; output withheld")
        return result.stdout.strip()
    original_env = dict(os.environ)
    try:
        compose("up", "-d")
        container = project+"-postgres-1"
        port = int(compose("port", "postgres", "5432").rsplit(":", 1)[1])
        pg = ExistingPostgres(container, port=port)
        for _ in range(80):
            try: pg.metadata(); break
            except TLSUpdateError: time.sleep(0.5)
        else: raise RuntimeError("Disposable PostgreSQL not ready")
        params = {"host": "127.0.0.1", "port": port, "user": "dpr_bootstrap", "password": password, "dbname": "postgres"}
        with psycopg.connect(**params, autocommit=True) as admin:
            for name in ("baseline_100k", "protected_734", "protected_100k", "baseline_1m", "protected_1m"):
                admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        pg.apply(root)
        params.update(sslmode="verify-full", sslrootcert=str(root/"postgres/tls/ca.crt"), gssencmode="disable")
        passwords = {role: secrets.token_urlsafe(36) for role in ROLES}
        profile = load_profile(REPO/"policy/protection_profile.yaml")
        provision(container, "protected_734", "dpr_bootstrap", passwords, profile)
        address = "https://127.0.0.1:"+compose("port", "openbao", "8200").rsplit(":", 1)[1]
        api = BaoAPI(address, str(root/"tls/ca.crt"))
        for _ in range(80):
            try: api.request("/sys/seal-status"); break
            except BaoError: time.sleep(0.5)
        initialize(api, root)
        material = json.loads((root/"openbao/init-material.json").read_text())
        for share in material["keys_base64"][:2]: unseal(api, share)
        configure(api, material["root_token"]); issue_tokens(api, material["root_token"], root, 3600)
        app_token = json.loads(next((root/"openbao/tokens").glob("svc-app-*.json")).read_text())["auth"]["client_token"]
        os.environ.update(OPENBAO_ADDR=address, OPENBAO_CACERT=str(root/"tls/ca.crt"), OPENBAO_VALIDATION_TOKEN=app_token)
        with OpenBaoClient(token_env="OPENBAO_VALIDATION_TOKEN") as client:
            rows = [synthetic_member(profile, i) for i in range(1, 18)]
            encrypted = protect_batch(rows, profile, client)
        columns = target_columns(profile)
        with psycopg.connect(**{**params, "dbname": "protected_734"}) as admin:
            query = sql.SQL("INSERT INTO public.anggota_protected ({}) VALUES ({})").format(sql.SQL(",").join(map(sql.Identifier, columns)), sql.SQL(",").join(sql.Placeholder() for _ in columns))
            with admin.cursor() as cursor: cursor.executemany(query, [[row[column] for column in columns] for row in encrypted])
        keys = (os.urandom(32), os.urandom(32)); store = artifact_store(str(folder/"archives"))
        backup_params = {**params, "dbname": "protected_734", "user": "backup_user", "password": passwords["backup_user"]}
        yield {"params": params, "backup_params": backup_params, "container": container, "keys": keys, "store": store, "profile": profile}
    finally:
        os.environ.clear(); os.environ.update(original_env)
        compose("down", "-v", "--remove-orphans")


def test_full_stream_restore_modes_tamper_retention(laboratory, monkeypatch):
    lab = laboratory; params = lab["params"]; keys = lab["keys"]; container = lab["container"]
    report = {"schema_version": 1, "passed": False, "scope": "17 invented records, disposable TLS PG18 and OpenBao", "checks": {}}
    checks = report["checks"]; restored = []
    try:
        with psycopg.connect(**lab["backup_params"]) as source:
            check_server(source, backup=True); before = row_counts(source)
        artifact = backup("protected_734", lab["backup_params"], keys, lab["store"], container=container)
        manifest = __import__("pathlib").Path(artifact["manifest"])
        payload = inspect_manifest(manifest, keys)
        checks["dump_backup_user_verified_tls"] = payload["dump_role"] == "backup_user"
        checks["snapshot_count_17"] = payload["source_rows"] == 17 and payload["table_rows"] == before
        with monkeypatch.context() as patch:
            patch.delenv("OPENBAO_VALIDATION_TOKEN", raising=False)
            without = restore(manifest, params, keys, container=container)
        restored.append(without["created_database"])
        checks["restore_without_openbao"] = without["decryption_smoke"]["performed"] is False
        with_keys = restore(manifest, params, keys, container=container, with_openbao=True)
        restored.append(with_keys["created_database"])
        checks["restore_with_openbao"] = with_keys["decryption_smoke"]["records"] == 16 and with_keys["decryption_smoke"]["authenticated_non_null_fields"] > 300
        checks["acl_ownership_rls_restored"] = all(with_keys["security"].values())
        with psycopg.connect(**{**params, "dbname": without["database"]}) as admin:
            admin.execute("SET ROLE app_user")
            checks["rls_denies_unscoped_app"] = admin.execute("SELECT count(*) FROM public.anggota_protected").fetchone()[0] == 0
            admin.execute("RESET ROLE"); admin.execute("SET ROLE analyst_user")
            checks["analyst_view_works"] = admin.execute("SELECT count(*) FROM public.analyst_view").fetchone()[0] == 17
        checks["tamper"] = tamper_test(manifest, params, keys, container=container)["passed"]
        retention = retention_test(manifest, params, lab["backup_params"], keys, lab["store"], container=container)
        checks["retention"] = retention["passed"] and retention["rows_before_delete"] == 18 and retention["rows_after_delete"] == 17
        with psycopg.connect(**lab["backup_params"]) as source:
            checks["original_source_unchanged"] = row_counts(source) == before
        checks["no_plaintext_dump_files"] = all(path.name.endswith((".dprbak", ".manifest.json")) or path.name == ".dpr-backup-store.json" for path in lab["store"].iterdir())
        with pytest.raises(BackupError): create_database(params, artifact["artifact_id"], "protected_734")
        with pytest.raises(psycopg.errors.DuplicateDatabase): create_database(params, artifact["artifact_id"], without["database"])
        with pytest.raises(BackupError): drop_created_database(params, {**without["created_database"], "oid": 0})
        with pytest.raises(BackupError): drop_created_database(params, {"name": "postgres"})
        with pytest.raises(BackupError): backup("postgres", lab["backup_params"], keys, lab["store"], container=container)
        with pytest.raises(BackupError): backup("protected_734", lab["backup_params"], keys, lab["store"], container=container, retention_days=0)
        with pytest.raises(BackupError): backup("protected_734", {**params, "dbname": "protected_734"}, keys, lab["store"], container=container)
        with pytest.raises(BackupError): smoke_decrypt(params, sample_size=101)
        with pytest.raises(BackupError): Tools("unsafe/target", params)
        with pytest.raises(BackupError): Tools(container, params).command("sh", [])
        with pytest.raises(BackupError): source_allowed("baseline_1m")
        checks["unsafe_inputs_existing_target_refused"] = True
        # Even a correctly signed hash cannot bypass AEAD with a wrong key or
        # corrupted encrypted bytes; both must fail BEFORE creating a database.
        wrong_key = os.urandom(32)
        modified = dict(payload); modified["encryption_key_id"] = key_id(wrong_key)
        original = manifest.read_bytes()
        try:
            manifest.write_bytes(canonical(sign_manifest(modified, keys[1])))
            with pytest.raises(BackupError, match="artifact_authentication_failed"):
                restore(manifest, params, (wrong_key, keys[1]), container=container)
        finally: manifest.write_bytes(original)
        encrypted_path = manifest.with_name(payload["artifact_id"]+".dprbak")
        original_encrypted = encrypted_path.read_bytes()
        broken = bytearray(original_encrypted); broken[len(broken)//2] ^= 1
        with psycopg.connect(**params) as admin:
            databases_before_failure = set(admin.execute("SELECT datname FROM pg_database").fetchall())
        try:
            encrypted_path.write_bytes(broken)
            manifest.write_bytes(canonical(sign_manifest({**payload, "sha256": hashlib.sha256(broken).hexdigest()}, keys[1])))
            with pytest.raises(BackupError, match="artifact_authentication_failed"):
                restore(manifest, params, keys, container=container)
        finally:
            encrypted_path.write_bytes(original_encrypted); manifest.write_bytes(original)
        checks["signed_digest_does_not_bypass_aead"] = True
        files_before_failure = set(lab["store"].iterdir())
        @contextmanager
        def failing_dump(self, program, arguments):
            from types import SimpleNamespace
            yield SimpleNamespace(stdout=io.BytesIO(b"invented-partial-archive"))
            raise BackupError("injected_dump_failure")
        with monkeypatch.context() as patch:
            patch.setattr(Tools, "process", failing_dump)
            with pytest.raises(BackupError): backup("protected_734", lab["backup_params"], keys, lab["store"], container=container)
        checks["failed_dump_leaves_no_artifact_or_manifest"] = set(lab["store"].iterdir()) == files_before_failure
        # A downstream failure must remove only its own newly created DB.
        from scripts.backup import runner
        with monkeypatch.context() as patch:
            patch.setattr(runner, "smoke_decrypt", lambda *args: (_ for _ in ()).throw(BackupError("injected")))
            with pytest.raises(BackupError): restore(manifest, params, keys, container=container, with_openbao=True)
        with psycopg.connect(**params) as admin:
            checks["failed_restore_cleanup"] = set(admin.execute("SELECT datname FROM pg_database").fetchall()) == databases_before_failure
        report["passed"] = all(checks.values())
        report["backup_seconds"] = artifact["backup_seconds"]; report["restore_seconds"] = with_keys["restore_seconds"]
        report["size_bytes"] = artifact["size_bytes"]
        assert report["passed"]
    finally:
        for created in reversed(restored):
            drop_created_database(params, created)
            drop_created_database(params, created)  # idempotent cleanup of this identity only
        destination = REPO/"evidence/backup/integration.json"; destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n", encoding="utf-8")
