"""Business-equivalent protected adapter using the public dprcrypto API and RLS."""

from datetime import date
import os
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
import yaml

from dprcrypto import BlindIndexer, KeyManager, OpenBaoClient, decrypt, encrypt
from datagen.model import COLUMNS
from migration.model import age_band, canonical_value, target_columns
from verify.profile import protection_plan

ROOT = Path(__file__).resolve().parents[2]
READS = ("read_by_nik", "read_by_email", "read_profile", "list_page")
INTEGERS = {"jumlah_anak", "jumlah_tanggungan", "jumlah_jiwa"}
DATES = {"tanggal_lahir", "tanggal_pernikahan"}


def protected_parameters(database):
    if database not in {"protected_100k", "protected_1m"}:
        raise ValueError("Unauthorized protected database")
    params = conninfo_to_dict(os.environ.get("PROTECTED_DATABASE_URL", ""))
    if ((params.get("host"), params.get("port"), params.get("user")) !=
            ("127.0.0.1", "5433", "app_user") or params.get("sslmode") != "verify-full"
            or not params.get("sslrootcert")):
        raise ValueError("Protected workload requires app_user and verify-full")
    params.update(dbname=database, application_name="dpr-protected-benchmark", connect_timeout=10,
                  options="-c statement_timeout=10000", gssencmode="disable")
    return params


def business_value(column, value):
    if value is None:
        return None
    if column in DATES:
        return date.fromisoformat(value)
    if column in INTEGERS:
        return int(value)
    return value


def decrypt_rows(rows, fields, profile, manager):
    """Unwrap only needed domains, once per batch; AAD always uses internal UUID."""
    deks = {}
    for domain, kek, wrapped in (("PII", "pii-kek", "dek_pii_wrapped"),
                                  ("FIN", "finance-kek", "dek_fin_wrapped")):
        needed = any(c != "id" and profile["columns"][c]["aead"] and
                     profile["columns"][c]["domain"] == domain for c in fields)
        if needed and rows:
            deks[domain] = manager.unwrap_many(kek, [r[wrapped] for r in rows])
    output = []
    for i, row in enumerate(rows):
        values = []
        for column in fields:
            if column == "id":
                values.append(row["legacy_row_id"])
                continue
            config = profile["columns"][column]
            value = row[config["storage_column"]]
            if config["aead"]:
                value = decrypt(value, deks[config["domain"]][i], column=column,
                                anggota_id=row["anggota_id"], protection_version=row["protection_version"])
            values.append(business_value(column, value))
        output.append(tuple(values))
    return output


class ProtectedConnection:
    def __init__(self, connection, client):
        self.connection, self.client = connection, client
        ttl, entries = cache_configuration()
        self.manager = KeyManager(client, cache_ttl=ttl, max_entries=entries)
        self.indexer = BlindIndexer(client, key_version=1)

    def close(self):
        try:
            self.manager.close()
            self.client.close()
        finally:
            self.connection.close()


def cache_configuration():
    """Explicit opt-in; cache-off remains the default and a reproducible variant."""
    try:
        ttl = float(os.environ.get('DPR_BENCH_DEK_CACHE_TTL', '0'))
        entries = int(os.environ.get('DPR_BENCH_DEK_CACHE_ENTRIES', '4096'))
        if not 0 <= ttl <= 60 or not 0 <= entries <= 4096:
            raise ValueError()
        return ttl, entries if ttl else 0
    except (TypeError, ValueError):
        raise ValueError('Invalid bounded DEK cache configuration') from None


def protect_insert(template, profile, session):
    """Use toolkit AEAD/envelope APIs and one cross-column HMAC batch, v1 unchanged."""
    identity = str(uuid4())
    keys = session.manager.create_record_keys()
    result = {'anggota_id': identity, 'legacy_row_id': template['id'], 'protection_version': 1,
              'dek_pii_wrapped': keys.pii.wrapped, 'dek_fin_wrapped': keys.finance.wrapped,
              'age_band': age_band(template['tanggal_lahir'], profile)}
    indexed = []
    for column, config in profile['columns'].items():
        value = canonical_value(template[column])
        result[config['storage_column']] = encrypt(value,
            keys.pii.dek if config['domain'] == 'PII' else keys.finance.dek,
            column=column, anggota_id=identity) if config['aead'] else value
        if config['bidx']:
            indexed.append((column, value))
    digests = session.indexer.digests(indexed)
    for (column, _), value in zip(indexed, digests):
        result[profile['columns'][column]['bidx_column']] = value
    return result


class ProtectedAdapter:
    def __init__(self, keys, database="protected_100k", *, profile=None):
        protection_plan("protected_dump_no_key")
        self.profile = profile or yaml.safe_load((ROOT / "policy/protection_profile.yaml").read_text(encoding="utf-8"))
        self.keys, self.database = keys, database

    def telemetry(self, sessions):
        stats = [session.manager.cache_stats() for session in sessions]
        counts = {key: sum(item[key] for item in stats) for key in
                  ('hits', 'misses', 'remote_batches', 'entries', 'max_entries')}
        counts.update(ttl_seconds=max((item['ttl_seconds'] for item in stats), default=0),
                      workers=len(sessions))
        wire = [s.client.connection_stats() for s in sessions]
        for field in ('opened_connections', 'reused_connections', 'requests'):
            counts['http_' + field] = sum(s.get(field, 0) for s in wire if isinstance(s, dict))
        return counts

    def connect(self):
        principal = str(UUID(os.environ["DPR_BENCH_PRINCIPAL"]))
        conn = psycopg.connect(**protected_parameters(self.database), autocommit=True,
                               prepare_threshold=5, row_factory=dict_row)
        client = None
        try:
            identity = conn.execute("SELECT current_user AS role,ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()").fetchone()
            if identity != {"role": "app_user", "ssl": True}:
                raise ValueError("Unexpected protected connection identity")
            conn.execute("SELECT set_config('app.principal',%s,false)", (principal,))
            client = OpenBaoClient()
            client.require_policy("svc-app")
            return ProtectedConnection(conn, client)
        except Exception:
            if client is not None:
                client.close()
            conn.close()
            raise

    def select(self, session, fields, suffix, values):
        storage = ["anggota_id", "legacy_row_id", "protection_version"]
        for column in fields:
            if column == "id":
                continue
            config = self.profile["columns"][column]
            storage.append(config["storage_column"])
            if config["aead"]:
                storage.append(config["wrapped_dek_column"])
        query = sql.SQL("SELECT {} FROM public.anggota_protected ").format(
            sql.SQL(",").join(map(sql.Identifier, dict.fromkeys(storage)))) + suffix
        rows = session.connection.execute(query, values).fetchall()
        return rows, decrypt_rows(rows, fields, self.profile, session.manager)

    def execute(self, session, operation, index, worker):
        row = self.keys["profiles"][index % len(self.keys["profiles"])]
        expected = [tuple(row[c] for c in COLUMNS)]
        if operation in READS[:3]:
            column = {"read_by_nik": "no_ktp", "read_by_email": "email", "read_profile": "id"}[operation]
            lookup = row[column] if column == "id" else session.indexer.digest(column, row[column])
            stored = "legacy_row_id" if column == "id" else self.profile["columns"][column]["bidx_column"]
            _, actual = self.select(session, COLUMNS, sql.SQL("WHERE {}=%s").format(sql.Identifier(stored)), (lookup,))
        elif operation == "list_page":
            page = self.keys["pages"][index % len(self.keys["pages"])]
            _, actual = self.select(session, ("id", "nama", "jenis_kelamin"),
                                    sql.SQL("WHERE legacy_row_id>%s ORDER BY legacy_row_id LIMIT %s"), (page["anchor"], 50))
            expected = [tuple(r) for r in page["rows"]]
        elif operation == "update_contact":
            contact = self.keys["insert_templates"][worker]["handphone"]
            with session.connection.transaction(force_rollback=True):
                record = session.connection.execute(
                    "SELECT anggota_id,legacy_row_id,protection_version,dek_pii_wrapped "
                    "FROM public.anggota_protected WHERE legacy_row_id=%s FOR UPDATE", (row["id"],)).fetchone()
                if record is None:
                    raise ValueError("Protected update target unavailable")
                dek = session.manager.unwrap_many("pii-kek", [record["dek_pii_wrapped"]])[0]
                ciphertext = encrypt(contact, dek, column="handphone", anggota_id=record["anggota_id"],
                                     protection_version=record["protection_version"])
                updated = session.connection.execute(
                    "UPDATE public.anggota_protected SET handphone_ct=%s WHERE anggota_id=%s RETURNING legacy_row_id,handphone_ct",
                    (ciphertext, record["anggota_id"])).fetchone()
                if updated is None:
                    raise ValueError("Protected update denied")
                actual = [(updated["legacy_row_id"], decrypt(updated["handphone_ct"], dek, column="handphone",
                           anggota_id=record["anggota_id"], protection_version=record["protection_version"]))]
                expected = [(row["id"], contact)]
        elif operation == "insert_member":
            template = dict(self.keys["insert_templates"][worker], id=-(worker + 1))
            protected = protect_insert(template, self.profile, session)
            columns = target_columns(self.profile)
            query = sql.SQL("INSERT INTO public.anggota_protected ({}) VALUES ({})").format(
                sql.SQL(",").join(map(sql.Identifier, columns)), sql.SQL(",").join(sql.Placeholder() for _ in columns))
            with session.connection.transaction(force_rollback=True):
                # AFTER INSERT grants creator scope before the separate SELECT.
                session.connection.execute(query, [protected[c] for c in columns])
                _, actual = self.select(session, COLUMNS, sql.SQL("WHERE legacy_row_id=%s"), (template["id"],))
                expected = [tuple(template[c] for c in COLUMNS)]
        else:
            raise ValueError("Unknown business operation")
        if actual != expected:
            raise ValueError("Business result mismatch (values withheld)")
        return actual
