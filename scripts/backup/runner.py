"""Snapshot-consistent dump, authenticated preflight and fresh database restore."""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import time
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from dprcrypto import OpenBaoClient, decrypt
from infra.protected.apply import load_profile
from infra.security import REPO, write_private
from infra.targets import PROTECTED_DATABASES
from .crypto import (BackupError, canonical, decrypt_stream, encrypt_stream, file_digest,
                     key_id, sign_manifest, verify_manifest)
from .postgres import (TABLES, Tools, allow_runtime_connections, check_restored_security, check_server, create_database,
                       drop_created_database, row_counts)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def source_allowed(database, created=None):
    if database in PROTECTED_DATABASES:
        return
    if not created or created["name"] != database:
        raise BackupError("only_protected_databases_or_owned_drills_can_be_backed_up")


def backup(database, parameters, keys, store, *, container="pg-dpr", retention_days=30, created=None):
    source_allowed(database, created)
    if type(retention_days) is not int or not 1 <= retention_days <= 3650:
        raise BackupError("invalid_retention_days")
    start = time.perf_counter(); identity = str(uuid4()); created_at = utc_now()
    encrypted = store / (identity+".dprbak")
    manifest = store / (identity+".manifest.json")
    encrypted_created = False
    connection_parameters = {**parameters, "dbname": database, "application_name": "dpr-backup-"+uuid4().hex}
    try:
        with psycopg.connect(**connection_parameters) as source:
            source.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            check_server(source, backup=True)
            if created:
                actual = source.execute("SELECT oid,shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()").fetchone()
                if actual != (created["oid"], created["marker"]):
                    raise BackupError("drill_database_identity_changed")
            counts = row_counts(source)
            snapshot = source.execute("SELECT pg_export_snapshot()").fetchone()[0]
            with Tools(container, connection_parameters) as tools:
                tools.bind()
                with tools.process("pg_dump", ["--format=custom", "--enable-row-security", "--snapshot="+snapshot]) as child:
                    fd = os.open(encrypted, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    encrypted_created = True
                    with os.fdopen(fd, "wb") as destination:
                        encrypt_stream(child.stdout, destination, keys[0], identity)
                        destination.flush(); os.fsync(destination.fileno())
        with encrypted.open("rb") as stream:
            digest, size = file_digest(stream)
        payload = {"format_version": 1, "artifact_id": identity, "created_at": created_at,
            "retention_deadline": (datetime.fromisoformat(created_at)+timedelta(days=retention_days)).isoformat(),
            "source_database": database, "source_rows": counts["anggota_protected"], "table_rows": counts,
            "sha256": digest, "size_bytes": size, "encryption": "AES-256-GCM-framed-HKDF-SHA256-v1",
            "encryption_key_id": key_id(keys[0]), "manifest_key_id": key_id(keys[1]),
            "postgres_major": 18, "dump_role": "backup_user", "snapshot_consistent": True,
            "backup_seconds": round(time.perf_counter()-start, 6)}
        write_private(manifest, canonical(sign_manifest(payload, keys[1]))+b"\n")
        return {**payload, "manifest": str(manifest)}
    except BaseException:
        # Only names allocated by this invocation can be removed; never a source.
        if encrypted_created:
            encrypted.unlink(missing_ok=True)
        raise


def inspect_manifest(manifest, keys):
    try:
        if manifest.stat().st_size > 65536:
            raise ValueError()
        payload = verify_manifest(json.loads(manifest.read_text(encoding="utf-8")), keys[1])
        identity = str(UUID(payload["artifact_id"]))
        if (identity != payload["artifact_id"] or manifest.name != identity+".manifest.json"
                or payload["format_version"] != 1 or payload["postgres_major"] != 18
                or payload["encryption"] != "AES-256-GCM-framed-HKDF-SHA256-v1"
                or payload["encryption_key_id"] != key_id(keys[0]) or payload["manifest_key_id"] != key_id(keys[1])
                or payload["dump_role"] != "backup_user" or payload["snapshot_consistent"] is not True
                or not re.fullmatch(r"[0-9a-f]{64}", payload["sha256"])
                or type(payload["size_bytes"]) is not int or payload["size_bytes"] < 60
                or set(payload["table_rows"]) != set(TABLES)
                or any(type(n) is not int or n < 0 for n in payload["table_rows"].values())
                or type(payload["source_rows"]) is not int or payload["source_rows"] != payload["table_rows"]["anggota_protected"]):
            raise ValueError()
        source_allowed(payload["source_database"], {"name": payload["source_database"]} if re.fullmatch(r"dpr_restore_[0-9a-f]{32}", payload["source_database"]) else None)
        created_at = datetime.fromisoformat(payload["created_at"])
        deadline = datetime.fromisoformat(payload["retention_deadline"])
        if created_at.tzinfo is None or deadline.tzinfo is None or deadline <= created_at:
            raise ValueError()
        return payload
    except (KeyError, ValueError, TypeError, AttributeError, OSError):
        raise BackupError("invalid_manifest") from None


def smoke_decrypt(parameters, profile_path=REPO/"policy/protection_profile.yaml", sample_size=16):
    if type(sample_size) is not int or not 1 <= sample_size <= 100:
        raise BackupError("invalid_decryption_sample_size")
    profile = load_profile(profile_path)
    fields = 0
    with OpenBaoClient(token_env="OPENBAO_VALIDATION_TOKEN") as client:
        client.require_policy("svc-app")
        with psycopg.connect(**parameters, row_factory=dict_row) as connection:
            connection.execute("SET TRANSACTION READ ONLY")
            records = connection.execute("SELECT * FROM public.anggota_protected ORDER BY legacy_row_id LIMIT %s", (sample_size,)).fetchall()
        pii = client.unwrap_batch("pii-kek", [row["dek_pii_wrapped"] for row in records])
        finance = client.unwrap_batch("finance-kek", [row["dek_fin_wrapped"] for row in records])
        for i, row in enumerate(records):
            for column, field in profile["columns"].items():
                if field["aead"]:
                    decrypt(row[field["storage_column"]], pii[i] if field["domain"] == "PII" else finance[i],
                        column=column, anggota_id=str(row["anggota_id"]), protection_version=row["protection_version"])
                    fields += row[field["storage_column"]] is not None
    return {"performed": True, "records": len(records), "authenticated_non_null_fields": fields,
            "domains": ["PII", "FIN"], "plaintext_written": False}


def restore(manifest, parameters, keys, *, container="pg-dpr", database=None,
            with_openbao=False, profile_path=REPO/"policy/protection_profile.yaml", sample_size=16):
    start = time.perf_counter(); manifest = Path(manifest)
    payload = inspect_manifest(manifest, keys)
    encrypted = manifest.with_name(payload["artifact_id"]+".dprbak")
    created = None
    # Keep the same file descriptor through hash, authentication and streaming.
    # Complete authentication precedes CREATE DATABASE, even for a wrong key.
    with encrypted.open("rb") as stream:
        digest, size = file_digest(stream)
        if digest != payload["sha256"] or size != payload["size_bytes"]:
            raise BackupError("encrypted_artifact_digest_mismatch")
        stream.seek(0); decrypt_stream(stream, None, keys[0], payload["artifact_id"])
        if with_openbao:
            # Validate the optional capability before allocating a database.
            with OpenBaoClient(token_env="OPENBAO_VALIDATION_TOKEN") as client:
                client.require_policy("svc-app")
        try:
            created = create_database(parameters, payload["artifact_id"], database)
            target_parameters = {**parameters, "dbname": created["name"], "application_name": "dpr-restore-"+uuid4().hex}
            with psycopg.connect(**target_parameters) as probe, Tools(container, target_parameters) as tools:
                check_server(probe); tools.bind()
                stream.seek(0)
                with tools.process("pg_restore", ["--single-transaction", "--exit-on-error", "--dbname="+created["name"]]) as child:
                    decrypt_stream(stream, child.stdin, keys[0], payload["artifact_id"])
            with psycopg.connect(**target_parameters) as connection:
                counts = row_counts(connection)
                if counts != payload["table_rows"]:
                    raise BackupError("restored_row_count_mismatch")
                security = check_restored_security(connection)
            smoke = smoke_decrypt(target_parameters, profile_path, sample_size) if with_openbao else {"performed": False, "reason": "without_openbao", "data_remains_field_ciphertext": True}
            allow_runtime_connections(target_parameters)
            return {"schema_version": 1, "passed": True, "artifact_id": payload["artifact_id"],
                "created_at": utc_now(), "database": created["name"], "mode": "with_openbao" if with_openbao else "without_openbao",
                "source_database": payload["source_database"], "table_rows": counts, "source_rows": payload["source_rows"],
                "manifest_hmac_verified": True, "sha256_verified": True, "all_frames_authenticated_before_restore": True,
                "security": security, "decryption_smoke": smoke, "size_bytes": size,
                "backup_seconds": payload["backup_seconds"], "restore_seconds": round(time.perf_counter()-start, 6),
                "created_database": created, "plaintext_dump_files": 0,
                "service_scope": "database, ACL/RLS and optional field decryption; HTTP app integration is separate"}
        except BaseException:
            if created: drop_created_database(parameters, created)
            raise
