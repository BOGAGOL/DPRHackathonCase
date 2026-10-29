"""Private exact-value ledger; full-row HMAC set, indexed fallback for partial rows."""
from collections import Counter
import hashlib
import hmac
import json
import secrets
import sqlite3

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from benchmark.common import parameters, utc_now
from datagen.model import COLUMNS, canonical
from .artifacts import private_path
from .profile import SENSITIVE, DIRECT

FIELDS = ",".join('"' + c + '"' for c in COLUMNS)


def normalized(row):
    return [None if row[c] is None else str(row[c]) for c in COLUMNS]


def row_mac(key, values):
    message = json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hmac.digest(key, message, "sha256")


def export_rows(path, rows, expected_checksum):
    """All raw cells and the ephemeral matching key remain in private SQLite."""
    path = private_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb"):
        pass
    connection = sqlite3.connect(path)
    key = secrets.token_bytes(32)
    checksum = hashlib.sha256()
    counts = {scope: Counter() for scope in ("all", "source_734", "synthetic")}
    totals = Counter()
    try:
        connection.execute("CREATE TABLE known (id INTEGER PRIMARY KEY," +
                           ",".join('"' + c + '" TEXT' for c in COLUMNS[1:]) + ",row_mac BLOB NOT NULL)")
        connection.execute("CREATE TABLE metadata (payload TEXT NOT NULL, matching_key BLOB NOT NULL)")
        insert = "INSERT INTO known VALUES (" + ",".join("?" for _ in range(len(COLUMNS) + 1)) + ")"
        batch = []
        for row in rows:
            checksum.update(canonical(row))
            values = normalized(row)
            scope = "source_734" if int(row["id"]) <= 734 else "synthetic"
            for group in ("all", scope):
                totals[group] += 1
                counts[group].update(c for c in SENSITIVE if row[c] is not None)
            batch.append((*values, row_mac(key, values)))
            if len(batch) == 4000:
                connection.executemany(insert, batch)
                batch.clear()
        if batch:
            connection.executemany(insert, batch)
        digest = checksum.hexdigest()
        if digest != expected_checksum:
            raise ValueError("Known-values source checksum differs from validated dataset")
        meta = {"format_version": 1, "created_at_utc": utc_now(), "baseline_checksum_sha256": digest,
                "rows": totals["all"], "population_rows": dict(totals), "sensitive_columns": list(SENSITIVE),
                "direct_identifiers": list(DIRECT), "non_null_cells": {g: dict(v) for g, v in counts.items()}}
        connection.execute("INSERT INTO metadata VALUES (?,?)", (json.dumps(meta), key))
        connection.commit()
        return meta
    finally:
        connection.close()


def export_database(path, database, expected_checksum):
    with psycopg.connect(**parameters(database), row_factory=dict_row) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        with conn.cursor(name="private_known_values") as cursor:
            cursor.itersize = 10000
            cursor.execute(sql.SQL("SELECT {} FROM public.anggota ORDER BY id").format(sql.SQL(FIELDS)))
            return export_rows(path, cursor, expected_checksum)


class KnownValues:
    def __init__(self, path):
        path = private_path(path)
        if not path.is_file():
            raise ValueError("Known-values file missing")
        self.connection = sqlite3.connect(path)
        # GROUP BY must not spill plaintext sort keys into the OS temp folder.
        self.connection.execute("PRAGMA temp_store=MEMORY")
        self.connection.execute("PRAGMA query_only=ON")
        payload, self.key = self.connection.execute("SELECT payload,matching_key FROM metadata").fetchone()
        self.meta = json.loads(payload)
        if self.meta.get("format_version") != 1:
            raise ValueError("Unsupported known-values format")

    def close(self):
        self.connection.close()

    def fingerprints(self):
        return {row[0] for row in self.connection.execute("SELECT row_mac FROM known")}

    def lookup(self, identifiers):
        """One indexed batch query, not one file search per known cell."""
        if not identifiers:
            return {}
        query = "SELECT " + FIELDS + " FROM known WHERE id IN (" + ",".join("?" for _ in identifiers) + ")"
        return {int(row[0]): [None if v is None else str(v) for v in row]
                for row in self.connection.execute(query, identifiers)}

    def equality(self):
        """SQLite groups exact known values; only frequency-of-frequencies exits."""
        output = []
        for column in COLUMNS[1:]:
            # Identifiers come exclusively from the fixed contract schema.
            histogram = self.connection.execute(
                'SELECT n,count(*) FROM (SELECT count(*) n FROM known WHERE "' + column +
                '" IS NOT NULL GROUP BY "' + column + '") GROUP BY n ORDER BY n').fetchall()
            output.append({"column": column, "storage": "plaintext", "equality_classes": sum(r[1] for r in histogram),
                           "largest_class": max((r[0] for r in histogram), default=0),
                           "non_null_cells": sum(r[0] * r[1] for r in histogram),
                           "frequency_histogram": [{"class_size": r[0], "number_of_classes": r[1]} for r in histogram]})
        return output
