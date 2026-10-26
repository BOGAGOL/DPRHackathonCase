import os

import pytest

from scanner.sources import database, read_database


@pytest.mark.skipif(not os.environ.get("SCANNER_TEST_DATABASE_URL"), reason="SCANNER_TEST_DATABASE_URL belum diatur")
def test_read_only_snapshot():
    # Never create, modify, or remove tables in the supplied database.
    with database(os.environ["SCANNER_TEST_DATABASE_URL"]) as conn:
        assert conn.execute("SHOW transaction_read_only").fetchone()[0] == "on"
        assert conn.execute("SHOW transaction_isolation").fetchone()[0] == "repeatable read"
        tables = read_database(conn, "public", 3)
        assert all(len(table.rows) <= 3 and table.total >= len(table.rows) for table in tables)
