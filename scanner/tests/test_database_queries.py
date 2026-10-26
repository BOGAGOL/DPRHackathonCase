"""Verify quoting and full-table aggregation without a running server."""
from scanner.model import Table
from scanner.sources import database_k, foreign_keys, read_database, safe_db_source


class Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0]


class Connection:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = []

    def execute(self, statement, parameters=None):
        rendered = statement if isinstance(statement, str) else statement.as_string()
        self.calls.append((rendered, parameters))
        return Result(next(self.results))


def test_quoted_identifiers_and_sample_limit():
    table, col, schema = 'odd";table', 'private";column', "sensitive-schema"
    conn = Connection([[(table, col, "text")], [(1000000,)], [("invented",)]])
    tables = read_database(conn, schema, 7)
    assert tables[0].total == 1000000
    assert conn.calls[0][1] == (schema, schema)
    assert conn.calls[2][1] == (7,)
    assert '"sensitive-schema"."odd"";table"' in conn.calls[2][0]
    assert '"private"";column"' in conn.calls[2][0]
    assert "ORDER BY random() LIMIT %s" in conn.calls[2][0]


def test_full_database_k_is_aggregate():
    conn = Connection([[(734, 730, 1, 732)]])
    table = Table("public.fixture", ["a", "b", "c"], ["text"] * 3)
    result = database_k(conn, table, [(0, 1, 2)], "public")[0]
    assert result["unique_rows"] == 730
    assert result["total_rows"] == 734
    assert result["scope"] == "full_database_aggregate"
    assert 'GROUP BY "a", "b", "c"' in conn.calls[0][0]
    assert "LIMIT" not in conn.calls[0][0]


def test_fk_catalog_fallback():
    conn = Connection([[], [("fk", "public", "child", "parent_id", "public", "parent", "id", 1)]])
    result = foreign_keys(conn, "public")
    assert result[0]["left_column"] == "parent_id"
    assert "information_schema" in conn.calls[0][0]
    assert "pg_catalog" in conn.calls[1][0]
    assert "has_table_privilege" in conn.calls[1][0]
    assert conn.calls[0][1] == conn.calls[1][1] == ("public",)


def test_safe_source_drops_credentials():
    source = safe_db_source("postgresql://invented:placeholder@127.0.0.1:5433/postgres?application_name=scanner")
    assert source == {"mode": "db", "host": "127.0.0.1", "port": "5433", "database": "postgres"}
