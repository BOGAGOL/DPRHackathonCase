from pathlib import Path

import pytest

from scanner.sources import DumpSource, InputError


@pytest.mark.parametrize("sql,expected", [
    ("CREATE TABLE `demo` (`a` varchar(100), `b` decimal(9,2), PRIMARY KEY (`a`));\n"
     "INSERT INTO `demo` VALUES ('Naya, Rekaan', 12.50),('O''Rekaan', NULL);", [("Naya, Rekaan", "12.50"), ("O'Rekaan", None)]),
    ('CREATE TABLE public.demo ("a" text, "b" text);\n'
     "INSERT INTO public.demo (b,a) VALUES ('x', 'satu'), (NULL, 'dua');", [("satu", "x"), ("dua", None)]),
    ('CREATE TABLE public.demo ("a" text, "b" text);\n'
     'COPY public.demo (a, b) FROM stdin;\nNaya\\tRekaan\tx\nDua\t\\N\n\\.\n', [("Naya\tRekaan", "x"), ("Dua", None)]),
    ("/*!40000 SQL_NO_CACHE */;\nCREATE TABLE `demo` (`a` text, `b` text);\n"
     "INSERT INTO `demo` VALUES ('x;--y', 'baris\\nbaru');", [("x;--y", "baris\nbaru")]),
    ("\\restrict synthetic-key\nCREATE TABLE public.demo (a text, b text);\n"
     "INSERT INTO public.demo VALUES ('satu','dua');\n\\unrestrict synthetic-key\n", [("satu", "dua")]),
    ("SET standard_conforming_strings = on; CREATE TABLE public.demo (a text, b text);"
     r"INSERT INTO public.demo VALUES ('a\b', E'baris\nbaru');", [(r"a\b", "baris\nbaru")]),
])
def test_dialects(tmp_path, sql, expected):
    path = tmp_path / "fixture.sql"
    path.write_text(sql, encoding="utf-8")
    source = DumpSource(100)
    try:
        tables = source.parse(path)
        assert len(tables) == 1
        assert tables[0].rows == expected
    finally:
        source.close()


def test_reservoir_full_dump_k_and_cleanup(sql_dump):
    source = DumpSource(3)
    temporary = Path(source.temp.name)
    try:
        table = source.parse(sql_dump)[0]
        assert len(table.rows) == 3
        assert table.total == 24
        result = source.k_anonymity(table, [(9, 11, 12)])[0]
        assert result["total_rows"] == 24
        assert result["unique_rows"] == 24
        assert result["scope"] == "full_dump_aggregate"
    finally:
        source.close()
    assert not temporary.exists()


@pytest.mark.parametrize("sql", [
    "INSERT INTO demo VALUES ('x');", "CREATE TABLE demo (a text); INSERT INTO demo VALUES (danger());",
    "CREATE TABLE demo (a text); COPY demo (a) FROM stdin;\nx\n",
    "CREATE TABLE demo (a text); INSERT INTO demo VALUES ('not closed);",
])
def test_fail_closed(tmp_path, sql):
    path = tmp_path / "bad.sql"
    path.write_text(sql, encoding="utf-8")
    source = DumpSource(5)
    try:
        with pytest.raises(InputError):
            source.parse(path)
    finally:
        source.close()
