"""Private pipe protocol. Never run with the other worker's credentials.

Operator: OpenBao key-operator token, no PG credentials and no decrypt policy.
Validator: scanner_user plus svc-app, no rotate/rewrap policy. Plaintext/HMAC
comparison state stays in this worker's memory and never crosses the pipe.
"""

import base64
from datetime import date, datetime
import hashlib
import hmac
import json
import os
import sys
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from dprcrypto import OpenBaoClient, decrypt
from infra.protected.apply import load_profile
from infra.security import REPO
from infra.targets import PROTECTED_DATABASES


class RotationError(RuntimeError):
    """Only fixed failure codes may leave the coordinator."""


def json_value(value):
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"bytes": base64.b64encode(value).decode("ascii")}
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    raise TypeError("Unsupported metadata type")


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=json_value).encode("utf-8")+b"\n"


def scan(database, client, key, *, progress=None):
    if database not in PROTECTED_DATABASES:
        raise RotationError("invalid_database")
    profile = load_profile(REPO/"policy/protection_profile.yaml")
    opaque = hashlib.sha256(); plaintext = hmac.new(key, digestmod=hashlib.sha256)
    deks = hmac.new(key, digestmod=hashlib.sha256); rows = 0; fields = 0
    params = {"dbname": database, "host": os.environ["PGHOST"], "port": int(os.environ["PGPORT"]),
        "user": os.environ["PGUSER"], "password": os.environ["PGPASSWORD"], "sslmode": "verify-full",
        "sslrootcert": os.environ["PGSSLROOTCERT"], "gssencmode": "disable", "connect_timeout": 10}
    with psycopg.connect(**params, row_factory=dict_row) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        identity = connection.execute("SELECT current_user AS name,current_setting('server_version_num')::int AS version,(SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()) AS tls").fetchone()
        if identity["name"] != "scanner_user" or identity["version"]//10000 != 18 or identity["tls"] is not True:
            raise RotationError("invalid_validation_role_or_tls")
        with connection.cursor(name="rotation_validation") as cursor:
            cursor.execute("SELECT * FROM public.anggota_protected ORDER BY legacy_row_id")
            while page := cursor.fetchmany(100):
                pii = client.unwrap_batch("pii-kek", [row["dek_pii_wrapped"] for row in page])
                finance = client.unwrap_batch("finance-kek", [row["dek_fin_wrapped"] for row in page])
                for index, row in enumerate(page):
                    identity = str(row["anggota_id"])
                    opaque.update(encoded({name: value for name, value in row.items() if name not in {"dek_pii_wrapped", "updated_at"}}))
                    deks.update(identity.encode("ascii")+pii[index]+finance[index])
                    decoded = {"anggota_id": identity}
                    for name, field in profile["columns"].items():
                        stored = row[field["storage_column"]]
                        decoded[name] = decrypt(stored, pii[index] if field["domain"] == "PII" else finance[index],
                            column=name, anggota_id=identity, protection_version=row["protection_version"]) if field["aead"] else stored
                        fields += bool(field["aead"] and stored is not None)
                    plaintext.update(encoded(decoded)); rows += 1
                if progress and rows % 10000 == 0: progress(rows)
    return {"rows": rows, "fields": fields, "opaque": opaque.digest(), "plaintext": plaintext.digest(), "deks": deks.digest()}


def operate(client, message):
    action = message["action"]
    if action == "metadata":
        return client.key_metadata("pii-kek")
    if action == "rotate":
        return client.rotate_key("pii-kek")
    if action == "rewrap":
        return client.rewrap_batch("pii-kek", message["wrapped"], key_version=message["version"])
    raise RotationError("invalid_operator_action")


class Validator:
    def __init__(self, client):
        self.client = client
        self.key = os.urandom(32)
        self.before = {}

    def request(self, message, *, progress=None):
        database = message["database"]; action = message["action"]
        if action not in {"before", "after"}:
            raise RotationError("invalid_validation_action")
        snapshot = scan(database, self.client, self.key, progress=progress)
        if action == "before":
            if database in self.before: raise RotationError("duplicate_baseline")
            self.before[database] = snapshot
            return {"rows": snapshot["rows"], "authenticated_fields": snapshot["fields"]}
        baseline = self.before.pop(database)
        checks = {"row_count_unchanged": snapshot["rows"] == baseline["rows"],
            "ciphertext_finance_bidx_ref_unchanged": hmac.compare_digest(snapshot["opaque"], baseline["opaque"]),
            "all_plaintext_values_unchanged": hmac.compare_digest(snapshot["plaintext"], baseline["plaintext"]),
            "all_record_deks_unchanged": hmac.compare_digest(snapshot["deks"], baseline["deks"])}
        if not all(checks.values()): raise RotationError("concurrent_or_unexpected_data_change")
        return {"passed": True, "rows": snapshot["rows"], "authenticated_fields": snapshot["fields"], **checks}


def serve(kind, incoming, outgoing):
    token_env = "OPENBAO_KEY_OPERATOR_TOKEN" if kind == "operator" else "OPENBAO_VALIDATION_TOKEN"
    policy = "key-operator" if kind == "operator" else "svc-app"
    if kind not in {"operator", "validator"}: raise RotationError("invalid_worker")
    if kind == "operator" and any(name in os.environ for name in ("PGPASSWORD", "PGUSER", "OPENBAO_VALIDATION_TOKEN")):
        raise RotationError("mixed_worker_credentials")
    if kind == "validator" and "OPENBAO_KEY_OPERATOR_TOKEN" in os.environ:
        raise RotationError("mixed_worker_credentials")
    with OpenBaoClient(token_env=token_env) as client:
        client.require_policy(policy)
        validator = Validator(client) if kind == "validator" else None
        for line in incoming:
            try:
                message = json.loads(line)
                def progress(rows):
                    outgoing.write(json.dumps({"progress_rows": rows})+"\n"); outgoing.flush()
                result = operate(client, message) if kind == "operator" else validator.request(message, progress=progress)
                response = {"ok": True, "result": result}
            except Exception:
                response = {"ok": False, "error": "worker_operation_failed_details_withheld"}
            outgoing.write(json.dumps(response)+"\n"); outgoing.flush()


if __name__ == "__main__":
    try:
        serve(sys.argv[1], sys.stdin, sys.stdout)
    except Exception:
        raise SystemExit(1) from None
