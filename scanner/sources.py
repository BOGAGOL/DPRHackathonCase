"""Read-only PostgreSQL access and a streaming, non-executing SQL dump reader."""
from contextlib import contextmanager
import json
from pathlib import Path
import random
import re
import sqlite3
import tempfile

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from .model import Table


class InputError(Exception):
    """Safe public error; do not attach database/parser exception messages."""


@contextmanager
def database(url):
    if not url:
        raise InputError("SCANNER_DATABASE_URL belum diatur di environment.")
    # Explicit read-only, consistent snapshot even when an administrator URL is
    # accidentally supplied. Do not log the DSN or any driver error details.
    with psycopg.connect(url, connect_timeout=10, autocommit=True) as conn:
        conn.execute("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        conn.execute("SET LOCAL statement_timeout = '120s'")
        try:
            yield conn
        finally:
            conn.execute("ROLLBACK")


def safe_db_source(url):
    info = conninfo_to_dict(url)
    return {"mode": "db", "host": info.get("host", "local"),
            "port": info.get("port", "5432"), "database": info.get("dbname", "")}


def read_database(conn, schema, sample):
    metadata = conn.execute(
        "SELECT table_name, column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name IN "
        "(SELECT table_name FROM information_schema.tables WHERE table_schema = %s "
        "AND table_type = 'BASE TABLE') ORDER BY table_name, ordinal_position", (schema, schema)
    ).fetchall()
    grouped = {}
    for name, column, kind in metadata:
        grouped.setdefault(name, ([], []))[0].append(column)
        grouped[name][1].append(kind)
    tables = []
    for name, (columns, types) in grouped.items():
        target = sql.Identifier(schema, name)
        total = conn.execute(sql.SQL("SELECT count(*) FROM {}").format(target)).fetchone()[0]
        query = sql.SQL("SELECT {} FROM {} ORDER BY random() LIMIT %s").format(
            sql.SQL(", ").join(map(sql.Identifier, columns)), target)
        rows = conn.execute(query, (sample,)).fetchall()
        tables.append(Table(schema + "." + name, columns, types, rows, total))
    return tables


def database_k(conn, table, combos, schema):
    result = []
    # The metadata table name is matched in the caller, never split on dots;
    # quoted identifiers may themselves contain dots.
    name = table.name[len(schema) + 1:]
    for combo in combos:
        columns = sql.SQL(", ").join(sql.Identifier(table.columns[i]) for i in combo)
        query = sql.SQL(
            "SELECT coalesce(sum(n),0), count(*) FILTER (WHERE n = 1), min(n), count(*) "
            "FROM (SELECT count(*) AS n FROM {} GROUP BY {}) AS grouped"
        ).format(sql.Identifier(schema, name), columns)
        total, unique, minimum, groups = conn.execute(query).fetchone()
        result.append({"table": table.name, "columns": [table.columns[i] for i in combo],
                       "total_rows": int(total), "unique_rows": unique, "k_min": minimum or 0,
                       "groups": groups, "scope": "full_database_aggregate",
                       "null_policy": "NULL values form a group; no row values exported"})
    return result


def foreign_keys(conn, schema):
    rows = conn.execute(
        "SELECT tc.constraint_name, tc.table_schema, tc.table_name, kcu.column_name, "
        "ukcu.table_schema, ukcu.table_name, ukcu.column_name, kcu.ordinal_position "
        "FROM information_schema.table_constraints tc "
        "JOIN information_schema.key_column_usage kcu ON "
        "(tc.constraint_catalog,tc.constraint_schema,tc.constraint_name) = "
        "(kcu.constraint_catalog,kcu.constraint_schema,kcu.constraint_name) "
        "AND tc.table_schema = kcu.table_schema AND tc.table_name = kcu.table_name "
        "JOIN information_schema.referential_constraints rc ON "
        "(tc.constraint_catalog,tc.constraint_schema,tc.constraint_name) = "
        "(rc.constraint_catalog,rc.constraint_schema,rc.constraint_name) "
        "JOIN information_schema.key_column_usage ukcu ON "
        "(ukcu.constraint_catalog,ukcu.constraint_schema,ukcu.constraint_name) = "
        "(rc.unique_constraint_catalog,rc.unique_constraint_schema,rc.unique_constraint_name) "
        "AND ukcu.ordinal_position = kcu.position_in_unique_constraint "
        "WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = %s "
        "ORDER BY tc.constraint_name, kcu.ordinal_position", (schema,)
    ).fetchall()
    # information_schema.referential_constraints can hide FKs from SELECT-only
    # users. pg_catalog exposes metadata without granting table writes.
    if not rows:
        rows = conn.execute(
            "SELECT con.conname, ns.nspname, rel.relname, src.attname, "
            "tns.nspname, target.relname, dst.attname, keys.position "
            "FROM pg_catalog.pg_constraint con "
            "JOIN pg_catalog.pg_class rel ON rel.oid = con.conrelid "
            "JOIN pg_catalog.pg_namespace ns ON ns.oid = rel.relnamespace "
            "JOIN pg_catalog.pg_class target ON target.oid = con.confrelid "
            "JOIN pg_catalog.pg_namespace tns ON tns.oid = target.relnamespace "
            "CROSS JOIN LATERAL unnest(con.conkey, con.confkey) WITH ORDINALITY "
            "AS keys(source_num, target_num, position) "
            "JOIN pg_catalog.pg_attribute src ON src.attrelid = con.conrelid AND src.attnum = keys.source_num "
            "JOIN pg_catalog.pg_attribute dst ON dst.attrelid = con.confrelid AND dst.attnum = keys.target_num "
            "WHERE con.contype = 'f' AND ns.nspname = %s "
            "AND has_table_privilege(con.conrelid, 'SELECT') "
            "ORDER BY con.conname, keys.position", (schema,)
        ).fetchall()
    return [{"constraint": r[0], "left_table": r[1] + "." + r[2], "left_column": r[3],
             "right_table": r[4] + "." + r[5], "right_column": r[6], "position": r[7]} for r in rows]


class SQLStream:
    """Small lexer: does not interpret SQL functions or execute input."""
    def __init__(self, handle):
        self.handle = handle
        self.char = ""
        self.pending = None
        self.backslash_escapes = False

    def get(self):
        if self.char:
            char, self.char = self.char, ""
            return char
        return self.handle.read(1)

    def token(self):
        if self.pending is not None:
            token, self.pending = self.pending, None
            return token
        while True:
            char = self.get()
            if not char:
                return None
            if char.isspace():
                continue
            if char in "-/#":
                second = self.get()
                if char == "#" or char == "-" and second == "-":
                    while second and second != "\n":
                        second = self.get()
                    continue
                if char == "/" and second == "*":
                    previous = ""
                    while True:
                        current = self.get()
                        if not current:
                            raise InputError("Komentar dump tidak ditutup.")
                        if previous == "*" and current == "/":
                            break
                        previous = current
                    continue
                self.char = second
            escape_string = False
            if char in "eE":
                second = self.get()
                if second == "'":
                    char = "'"
                    escape_string = True
                else:
                    self.char = second
            if char == "`":
                self.backslash_escapes = True
            if char in "'\"`":
                quote, pieces = char, []
                while True:
                    current = self.get()
                    if not current:
                        raise InputError("String dump tidak ditutup.")
                    if current == quote:
                        second = self.get()
                        if second == quote:
                            pieces.append(quote)
                            continue
                        self.char = second
                        break
                    if current == "\\" and quote == "'" and (self.backslash_escapes or escape_string):
                        escaped = self.get()
                        pieces.append({"n": "\n", "r": "\r", "t": "\t", "0": "\0"}.get(escaped, escaped))
                    else:
                        pieces.append(current)
                return ("value" if quote == "'" else "identifier", "".join(pieces))
            if char in "(),;.":
                return ("punct", char)
            pieces = [char]
            while True:
                current = self.get()
                if not current or current.isspace() or current in "(),;.\"'`":
                    self.char = current
                    break
                pieces.append(current)
            return ("word", "".join(pieces))

    def peek(self):
        if self.pending is None:
            self.pending = self.token()
        return self.pending

    def expect(self, value):
        token = self.token()
        if token is None or token[1].upper() != value.upper():
            raise InputError("Struktur SQL dump tidak didukung atau tidak lengkap.")
        return token

    def skip_statement(self):
        while (token := self.token()) is not None:
            if token[1] == ";":
                return

    def identifier(self):
        token = self.token()
        if token is None or token[0] not in {"word", "identifier"}:
            raise InputError("Identifier dump tidak valid.")
        parts = [token[1]]
        while self.peek() == ("punct", "."):
            self.token()
            token = self.token()
            if token is None:
                raise InputError("Identifier dump tidak lengkap.")
            parts.append(token[1])
        return ".".join(parts) if len(parts) > 1 else "public." + parts[0]


def split_items(stream):
    """Read comma-separated parenthesized SQL, preserving nested type modifiers."""
    stream.expect("(")
    items, current, depth = [], [], 1
    while (token := stream.token()) is not None:
        if token == ("punct", "("):
            depth += 1
        elif token == ("punct", ")"):
            depth -= 1
            if depth == 0:
                if current:
                    items.append(current)
                return items
        if token == ("punct", ",") and depth == 1:
            items.append(current)
            current = []
        else:
            current.append(token)
    raise InputError("Daftar SQL dump tidak lengkap.")


def copy_unescape(text):
    return re.sub(r"\\([0-7]{1,3}|x[0-9a-fA-F]{1,2}|.)",
                  lambda m: chr(int(m[1], 16)) if m[1].startswith("x") else
                  chr(int(m[1], 8)) if m[1][0].isdigit() else
                  {"t": "\t", "n": "\n", "r": "\r", "b": "\b", "f": "\f", "v": "\v"}.get(m[1], m[1]), text)


class DumpSource:
    """Reservoir samples in RAM; full rows on a private temporary SQLite file.

    The temporary file is local plaintext input, deleted on close. It permits
    exact whole-dump k-anonymity without keeping a large dump in memory.
    """
    def __init__(self, sample):
        self.sample = sample
        self.tables = {}
        self.rng = random.Random(2026)
        self.temp = tempfile.TemporaryDirectory(prefix="scanner-")
        self.conn = sqlite3.connect(str(Path(self.temp.name) / "private.sqlite"))
        self.conn.execute("CREATE TABLE rows (table_name TEXT, payload TEXT)")

    def close(self):
        self.conn.close()
        self.temp.cleanup()

    def ensure(self, name, columns, types=None):
        if name not in self.tables:
            self.tables[name] = Table(name, columns, types or ["unknown"] * len(columns))
        elif self.tables[name].columns != columns:
            raise InputError("Definisi kolom dump berubah; scan dihentikan.")
        return self.tables[name]

    def append(self, table, row, source_columns):
        if len(row) != len(source_columns) or any(c not in table.columns for c in source_columns):
            raise InputError("Jumlah atau nama kolom dump tidak sesuai definisi.")
        mapping = dict(zip(source_columns, row))
        full = tuple(mapping.get(c) for c in table.columns)
        table.total += 1
        self.conn.execute("INSERT INTO rows VALUES (?, ?)", (table.name, json.dumps(full)))
        if len(table.rows) < self.sample:
            table.rows.append(full)
        else:
            index = self.rng.randrange(table.total)
            if index < self.sample:
                table.rows[index] = full

    def parse(self, path):
        with Path(path).open(encoding="utf-8-sig", errors="strict", newline="") as handle:
            stream = SQLStream(handle)
            while (token := stream.token()) is not None:
                if token == ("punct", ";"):
                    continue
                if token[0] != "word":
                    stream.skip_statement()
                    continue
                command = token[1].upper()
                if command == "CREATE":
                    next_token = stream.token()
                    if next_token is None or next_token[1].upper() != "TABLE":
                        stream.skip_statement()
                        continue
                    if stream.peek() and stream.peek()[1].upper() == "IF":
                        stream.expect("IF"); stream.expect("NOT"); stream.expect("EXISTS")
                    name = stream.identifier()
                    if stream.peek() != ("punct", "("):
                        raise InputError("CREATE TABLE tanpa daftar kolom tidak didukung.")
                    items = split_items(stream)
                    definitions = [item for item in items if item and
                                   (item[0][0] == "identifier" or item[0][1].upper() not in
                                    {"PRIMARY", "FOREIGN", "CONSTRAINT", "KEY", "UNIQUE", "CHECK", "INDEX"})]
                    self.ensure(name, [d[0][1] for d in definitions],
                                [d[1][1] if len(d) > 1 else "unknown" for d in definitions])
                    stream.skip_statement()
                elif command == "INSERT":
                    stream.expect("INTO")
                    name = stream.identifier()
                    explicit = stream.peek() == ("punct", "(")
                    columns = [item[0][1] for item in split_items(stream)] if explicit else None
                    if columns is None and name not in self.tables:
                        raise InputError("INSERT tanpa daftar kolom memerlukan CREATE TABLE.")
                    table = self.tables.get(name) or self.ensure(name, columns)
                    columns = columns or table.columns
                    stream.expect("VALUES")
                    while True:
                        items = split_items(stream)
                        row = []
                        for item in items:
                            if len(item) == 1:
                                row.append(None if item[0][0] == "word" and item[0][1].upper() == "NULL" else item[0][1])
                            elif len(item) == 3 and item[0][0] == item[2][0] == "word" and item[1] == ("punct", "."):
                                row.append(item[0][1] + "." + item[2][1])
                            else:
                                raise InputError("Ekspresi INSERT tidak didukung; hanya literal SQL diperbolehkan.")
                        self.append(table, row, columns)
                        if stream.peek() != ("punct", ","):
                            stream.expect(";")
                            break
                        stream.token()
                elif command == "COPY":
                    name = stream.identifier()
                    columns = [item[0][1] for item in split_items(stream)]
                    stream.expect("FROM"); stream.expect("STDIN"); stream.expect(";")
                    table = self.tables.get(name) or self.ensure(name, columns)
                    # Semicolon token has no lookahead. Consume the remaining header
                    # newline, then PostgreSQL text COPY lines directly.
                    if stream.char:
                        raise InputError("Posisi COPY dump tidak valid.")
                    tail = handle.readline()
                    if tail.strip():
                        raise InputError("Header COPY harus diakhiri baris baru.")
                    for line in handle:
                        raw = line.rstrip("\r\n")
                        if raw == "\\.":
                            break
                        row = [None if value == r"\N" else copy_unescape(value) for value in raw.split("\t")]
                        self.append(table, row, columns)
                    else:
                        raise InputError("COPY dump tidak memiliki terminator.")
                elif command == "SET":
                    setting = []
                    while (token := stream.token()) is not None and token != ("punct", ";"):
                        setting.append(token[1].lower())
                    joined = " ".join(setting)
                    if "standard_conforming_strings" in setting:
                        stream.backslash_escapes = "off" in setting
                    elif "sql_mode" in joined and "no_backslash_escapes" in joined:
                        stream.backslash_escapes = False
                elif command in {"SELECT", "ALTER", "COMMENT", "GRANT", "REVOKE", "BEGIN", "COMMIT", "DROP", "LOCK", "UNLOCK"}:
                    stream.skip_statement()
                elif command.startswith("\\"):
                    # pg_dump v17+ \restrict / \unrestrict are line commands.
                    if stream.char != "\n":
                        handle.readline()
                    stream.char = ""
                else:
                    raise InputError("Perintah dump tidak didukung; input tidak pernah dieksekusi.")
        self.conn.commit()
        if not self.tables:
            raise InputError("Tidak ada tabel yang dapat dibaca dari dump.")
        return list(self.tables.values())

    def k_anonymity(self, table, combos):
        output = []
        for combo in combos:
            # Only fixed SQL fragments are repeated; JSON paths are bound parameters.
            expressions = ", ".join("json_extract(payload, ?)" for _ in combo)
            query = ("SELECT coalesce(sum(n),0), coalesce(sum(CASE WHEN n = 1 THEN 1 ELSE 0 END),0), "
                     "min(n), count(*) FROM (SELECT count(*) AS n FROM rows WHERE table_name = ? GROUP BY "
                     + expressions + ") AS grouped")
            paths = [f"$[{i}]" for i in combo]
            total, unique, minimum, groups = self.conn.execute(query, [table.name, *paths]).fetchone()
            output.append({"table": table.name, "columns": [table.columns[i] for i in combo],
                           "total_rows": total, "unique_rows": unique, "k_min": minimum or 0,
                           "groups": groups, "scope": "full_dump_aggregate",
                           "null_policy": "NULL values form a group; no row values exported"})
        return output
