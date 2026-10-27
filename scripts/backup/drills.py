"""Tamper rejection and deletion drills; only invocation-owned scratch DBs mutate."""

from pathlib import Path
import secrets
import tempfile
from uuid import uuid4

import psycopg
from psycopg import sql

from dprcrypto import OpenBaoClient
from infra.protected.apply import load_profile
from infra.security import REPO, write_private
from migration.model import protect_batch, target_columns
from .crypto import BackupError
from .postgres import drop_created_database, row_counts
from .runner import backup, inspect_manifest, restore, utc_now


def tamper_test(manifest, parameters, keys, *, container="pg-dpr"):
    manifest = Path(manifest); payload = inspect_manifest(manifest, keys)
    source = manifest.with_name(payload["artifact_id"]+".dprbak")
    # The disposable copy contains encrypted bytes only and is outside Git.
    with tempfile.TemporaryDirectory(prefix="tamper-", dir=manifest.parent) as folder:
        folder = Path(folder)
        write_private(folder / manifest.name, manifest.read_bytes())
        destination = folder / source.name
        with source.open("rb") as incoming, destination.open("xb") as outgoing:
            while chunk := incoming.read(1024*1024): outgoing.write(chunk)
        with destination.open("r+b") as stream:
            stream.seek(payload["size_bytes"]//2)
            original = stream.read(1)
            if len(original) != 1: raise BackupError("tamper_requires_valid_artifact")
            stream.seek(-1, 1); stream.write(bytes([original[0]^1]))
        try:
            unexpected = restore(folder/manifest.name, parameters, keys, container=container)
        except BackupError as error:
            if str(error) != "encrypted_artifact_digest_mismatch": raise
        else:
            drop_created_database(parameters, unexpected["created_database"])
            raise BackupError("tampered_artifact_was_accepted")
    return {"schema_version": 1, "passed": True, "created_at": utc_now(), "artifact_id": payload["artifact_id"],
        "modified_bytes": 1, "restore_rejected": True, "rejection": "encrypted_artifact_digest_mismatch",
        "rejected_before_database_creation": True, "original_unchanged": True}


def synthetic_member(profile, legacy_id):
    label = "retention-"+uuid4().hex
    row = {name: label for name in profile["columns"]}
    row.update(id=legacy_id, jenis_kelamin="L", tanggal_lahir="1986-10-02", tanggal_pernikahan=None,
        no_ktp="99"+str(secrets.randbelow(10**12)).zfill(12), email=label+"@example.invalid",
        pengguna=label, jumlah_anak=0, jumlah_tanggungan=0, jumlah_jiwa=1,
        pekerjaan_terakhir="Synthetic retention", nama_bank="Synthetic bank", nama_kppn="Synthetic office")
    return row


def retention_test(manifest, admin_parameters, backup_parameters, keys, store, *, container="pg-dpr",
                   profile_path=REPO/"policy/protection_profile.yaml", retention_days=30):
    profile = load_profile(profile_path)
    created = []; result = None
    with OpenBaoClient(token_env="OPENBAO_VALIDATION_TOKEN") as client:
        client.require_policy("svc-app")
        try:
            initial = restore(manifest, admin_parameters, keys, container=container)
            scratch = initial["created_database"]; created.append(scratch)
            params = {**admin_parameters, "dbname": scratch["name"]}
            with psycopg.connect(**params) as connection:
                actual = connection.execute("SELECT oid,shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()").fetchone()
                if actual != (scratch["oid"], scratch["marker"]):
                    raise BackupError("retention_requires_own_scratch_database")
                legacy = connection.execute("SELECT coalesce(max(legacy_row_id),0)+1 FROM public.anggota_protected").fetchone()[0]
                protected = protect_batch([synthetic_member(profile, legacy)], profile, client)[0]
                columns = target_columns(profile)
                connection.execute(sql.SQL("INSERT INTO public.anggota_protected ({}) VALUES ({})").format(
                    sql.SQL(",").join(map(sql.Identifier, columns)), sql.SQL(",").join(sql.Placeholder() for _ in columns)),
                    [protected[column] for column in columns])
            before = backup(scratch["name"], backup_parameters, keys, store, container=container, retention_days=retention_days, created=scratch)
            before_restore = restore(before["manifest"], admin_parameters, keys, container=container)
            created.append(before_restore["created_database"])
            with psycopg.connect(**{**admin_parameters, "dbname": before_restore["database"]}) as connection:
                present = connection.execute("SELECT count(*) FROM public.anggota_protected WHERE anggota_id=%s AND legacy_row_id=%s", (protected["anggota_id"], legacy)).fetchone()[0] == 1
            if not present: raise BackupError("retention_control_record_not_present")
            with psycopg.connect(**params) as connection:
                removed = connection.execute("DELETE FROM public.anggota_protected WHERE anggota_id=%s AND legacy_row_id=%s", (protected["anggota_id"], legacy)).rowcount
                if removed != 1: raise BackupError("retention_did_not_delete_exactly_one_synthetic_member")
            after = backup(scratch["name"], backup_parameters, keys, store, container=container, retention_days=retention_days, created=scratch)
            after_restore = restore(after["manifest"], admin_parameters, keys, container=container, with_openbao=True, profile_path=profile_path)
            created.append(after_restore["created_database"])
            with psycopg.connect(**{**admin_parameters, "dbname": after_restore["database"]}) as connection:
                absent = connection.execute("SELECT count(*) FROM public.anggota_protected WHERE anggota_id=%s OR legacy_row_id=%s", (protected["anggota_id"], legacy)).fetchone()[0] == 0
            if not absent or before["source_rows"]-after["source_rows"] != 1:
                raise BackupError("retention_deleted_member_reappeared")
            result = {"schema_version": 1, "passed": True, "created_at": utc_now(),
                "scope": "new invented member in invocation-owned restore clone only",
                "control_backup_contains_member": present, "new_backup_restore_member_absent": absent,
                "rows_before_delete": before["source_rows"], "rows_after_delete": after["source_rows"],
                "before_artifact_id": before["artifact_id"], "after_artifact_id": after["artifact_id"],
                "original_source_not_modified": True, "old_backup_still_contains_member_until_expiry": True,
                "physical_secure_erasure_claimed": False, "decryption_smoke": after_restore["decryption_smoke"]}
        finally:
            for database in reversed(created): drop_created_database(admin_parameters, database)
    result["scratch_databases_removed"] = len(created)
    return result
