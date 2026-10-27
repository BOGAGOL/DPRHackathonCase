from datetime import date
import json
from unittest.mock import MagicMock

import pytest

from datagen.model import COLUMNS
from benchmark.adapters import plaintext as plain


def test_all_operations_semantics_and_forced_rollback(source):
    keys = {"profiles": source, "pages": [{"anchor": 0, "rows": [[1, source[0]["nama"], "L"]]}], "insert_templates": source[:8]}
    adapter = plain.PlaintextAdapter(keys)
    conn = MagicMock()
    for op in ("read_by_nik", "read_by_email", "read_profile"):
        conn.execute.return_value.fetchall.return_value = [tuple(source[0][c] for c in COLUMNS)]
        adapter.execute(conn, op, 0, 0)
        assert conn.execute.call_args.args[1] == (source[0][{"read_by_nik":"no_ktp","read_by_email":"email","read_profile":"id"}[op]],)
    conn.execute.return_value.fetchall.return_value = [tuple(keys["pages"][0]["rows"][0])]
    adapter.execute(conn, "list_page", 0, 0)
    conn.execute.return_value.fetchone.return_value = (source[0]["id"], source[0]["handphone"])
    adapter.execute(conn, "update_contact", 0, 0)
    template = dict(source[0], id=-1)
    conn.execute.return_value.fetchone.return_value = tuple(template[c] for c in COLUMNS)
    adapter.execute(conn, "insert_member", 0, 0)
    assert conn.transaction.call_count == 2
    assert all(c.kwargs["force_rollback"] for c in conn.transaction.call_args_list)
    assert "OVERRIDING SYSTEM VALUE" in plain.INSERT.as_string()
    conn.execute.return_value.fetchall.return_value = []
    with pytest.raises(ValueError, match="withheld"):
        adapter.execute(conn, "read_profile", 0, 0)
    with pytest.raises(ValueError):
        adapter.execute(conn, "unknown", 0, 0)


def test_connect_uses_env_and_prepared_statements(monkeypatch):
    monkeypatch.setattr(plain, "parameters", lambda: {"dbname": "baseline_100k"})
    connect = MagicMock()
    monkeypatch.setattr(plain.psycopg, "connect", connect)
    plain.PlaintextAdapter({}).connect()
    assert connect.call_args.kwargs["autocommit"] and connect.call_args.kwargs["prepare_threshold"] == 5


def test_existing_private_keys_dates_and_config_guard(monkeypatch, tmp_path, source):
    monkeypatch.setattr(plain, "private_directory", lambda: tmp_path)
    path = tmp_path / "baseline_100k_keys_v1.json"
    path.write_text(json.dumps({"version":1,"seed":42,"concurrency":8,"profiles":source,
                               "pages":[{"anchor":0,"rows":[]}],"insert_templates":source[:8]}, default=str))
    payload, report = plain.load_keys({"seed":42}, 8)
    assert isinstance(payload["profiles"][0]["tanggal_lahir"], date)
    assert "profiles" not in report and "sha256" in report
    with pytest.raises(ValueError):
        plain.load_keys({"seed":99}, 8)


def test_new_corpus_is_exclusive_and_queries_are_bound(monkeypatch, tmp_path, source):
    monkeypatch.setattr(plain, "private_directory", lambda: tmp_path)
    monkeypatch.setattr(plain, "parameters", lambda: {})
    conn = MagicMock()
    conn.__enter__.return_value = conn
    first = MagicMock(); first.__iter__.return_value = iter({"id":r["id"]} for r in source)
    second = MagicMock(); second.fetchall.return_value = source
    page = MagicMock(); page.fetchall.return_value = [{"id":1,"nama":source[0]["nama"],"jenis_kelamin":"L"}]
    empty = MagicMock(); empty.fetchone.return_value = {"exists":False}
    conn.execute.side_effect = [first, second, page] + [empty] * 9
    monkeypatch.setattr(plain.psycopg, "connect", lambda **k: conn)
    payload, info = plain.load_keys({"seed":42,"key_pool":40,"page_pool":1,"page_size":50}, 2)
    assert len(payload["insert_templates"]) == 2 and info["profile_count"] == 40
    assert (tmp_path / "baseline_100k_keys_v1.json").exists()
    assert all(len(c.args) == 2 for c in conn.execute.call_args_list[1:])
