"""Canonical source encoding and profile-driven field AEAD; never log row values."""

from datetime import date, datetime
import json
import os
from uuid import uuid4

from dprcrypto import decrypt, encrypt, index_message


class MigrationError(RuntimeError):
    """Only fixed, non-sensitive failure codes may reach CLI evidence."""

    def __init__(self, code: str):
        allowed = {"unsupported_source_type","invalid_birth_date","invalid_hmac_batch","crypto_batch_too_large",
            "invalid_wrap_batch","validation_row_count","validation_key_count","validation_identity",
            "validation_field_mismatch","validation_age_band","validation_blind_index","invalid_source_target_pair",
            "invalid_source_id","wrong_database_or_version","unsafe_target_role","target_not_fresh",
            "source_or_profile_changed","target_checkpoint_mismatch","concurrent_checkpoint_change",
            "validation_totals_or_nulls","validation_index_uniqueness","invalid_batch_bound",
            "validation_identity_not_separate","migration_already_running","migration_incomplete",
            "source_changed_during_migration","invalid_prepare_target","schema_inspection_failed",
            "missing_target_credential","missing_migration_token"}
        allowed.update({"invalid_expected_row_count","unexpected_source_row_count"})
        self.code = code if code in allowed else "migration_failed"
        super().__init__(self.code)


def canonical_value(value):
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if type(value) is int:
        return str(value)
    raise MigrationError("unsupported_source_type")


def source_bytes(row: dict, columns: list[str]) -> bytes:
    return (json.dumps([row["id"], *[canonical_value(row[column]) for column in columns]],
                       ensure_ascii=False, separators=(",", ":"))+"\n").encode("utf-8")


def age_band(value, profile: dict) -> str | None:
    if value is None:
        return None
    try:
        born = date.fromisoformat(canonical_value(value))
        reference = date.fromisoformat(profile["derived"]["age_band"]["reference_date"])
        years = reference.year-born.year-((reference.month, reference.day)<(born.month,born.day))
        if years < 0:
            raise ValueError()
        lower = years//10*10
        return f"{lower}-{lower+9}"
    except (ValueError, TypeError):
        raise MigrationError("invalid_birth_date") from None


def target_columns(profile: dict) -> list[str]:
    return ["anggota_id","legacy_row_id","protection_version","dek_pii_wrapped","dek_fin_wrapped",
            *[field["storage_column"] for field in profile["columns"].values()],
            *[field["bidx_column"] for field in profile["columns"].values() if field["bidx"]], "age_band"]


def blind_indexes(client, column: str, values: list, version: int) -> list:
    positions = [i for i,value in enumerate(values) if value is not None]
    digests = client.hmac_batch([index_message(column, canonical_value(values[i])) for i in positions], key_version=version)
    if len(digests) != len(positions):
        raise MigrationError("invalid_hmac_batch")
    result = [None]*len(values)
    for i,digest in zip(positions,digests): result[i] = digest
    return result


def protect_batch(rows: list[dict], profile: dict, client) -> list[dict]:
    """At most 100 records of plaintext DEKs live in this frame; wrap in Transit."""
    if len(rows)>100:
        raise MigrationError("crypto_batch_too_large")
    pii = [os.urandom(32) for _ in rows]
    finance = [os.urandom(32) for _ in rows]
    wrapped_pii = client.wrap_batch("pii-kek",pii)
    wrapped_fin = client.wrap_batch("finance-kek",finance)
    if len(wrapped_pii)!=len(rows) or len(wrapped_fin)!=len(rows):
        raise MigrationError("invalid_wrap_batch")
    result = []
    for i,row in enumerate(rows):
        identity = str(uuid4())
        protected = {"anggota_id":identity,"legacy_row_id":row["id"],"protection_version":1,
                     "dek_pii_wrapped":wrapped_pii[i],"dek_fin_wrapped":wrapped_fin[i],
                     "age_band":age_band(row["tanggal_lahir"],profile)}
        for column,field in profile["columns"].items():
            value = canonical_value(row[column])
            protected[field["storage_column"]] = (encrypt(value,pii[i] if field["domain"]=="PII" else finance[i],
                column=column,anggota_id=identity) if field["aead"] else value)
        result.append(protected)
    for column,field in profile["columns"].items():
        if field["bidx"]:
            digests = blind_indexes(client,column,[row[column] for row in rows],profile["blind_index"]["key_version"])
            for protected,digest in zip(result,digests): protected[field["bidx_column"]] = digest
    return result


def compare_batch(rows: list[dict], protected: list[dict], profile: dict, client) -> dict:
    """Full decrypt/compare, including NULL, REF, age bands and recomputed HMAC."""
    if len(rows)!=len(protected) or len(rows)>100:
        raise MigrationError("validation_row_count")
    pii = client.unwrap_batch("pii-kek",[row["dek_pii_wrapped"] for row in protected])
    finance = client.unwrap_batch("finance-kek",[row["dek_fin_wrapped"] for row in protected])
    if len(pii)!=len(rows) or len(finance)!=len(rows):
        raise MigrationError("validation_key_count")
    nulls = {column:0 for column in profile["columns"]}
    for i,(row,target) in enumerate(zip(rows,protected)):
        if row["id"]!=target["legacy_row_id"] or target["protection_version"]!=1:
            raise MigrationError("validation_identity")
        for column,field in profile["columns"].items():
            expected = canonical_value(row[column])
            stored = target[field["storage_column"]]
            actual = (decrypt(stored,pii[i] if field["domain"]=="PII" else finance[i], column=column,
                              anggota_id=str(target["anggota_id"]),protection_version=target["protection_version"])
                      if field["aead"] else stored)
            if expected!=actual:
                raise MigrationError("validation_field_mismatch")
            nulls[column] += expected is None
        if age_band(row["tanggal_lahir"],profile)!=target["age_band"]:
            raise MigrationError("validation_age_band")
    for column,field in profile["columns"].items():
        if field["bidx"]:
            values = blind_indexes(client,column,[row[column] for row in rows],profile["blind_index"]["key_version"])
            if any(value!=target[field["bidx_column"]] for value,target in zip(values,protected)):
                raise MigrationError("validation_blind_index")
    return nulls
