"""Business-equivalent plain adapter. All writes use ROLLBACK and explicit IDs."""

from datetime import date
import json
import random

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from datagen.model import COLUMNS, UNIQUE, generate
from ..common import BASELINE_ROWS, parameters, private_directory, file_hash

SELECT = sql.SQL("SELECT {} FROM public.anggota ").format(sql.SQL(",").join(map(sql.Identifier, COLUMNS)))
INSERT = sql.SQL("INSERT INTO public.anggota ({}) OVERRIDING SYSTEM VALUE VALUES ({}) RETURNING {}").format(
    sql.SQL(",").join(map(sql.Identifier, COLUMNS)), sql.SQL(",").join(sql.Placeholder() for _ in COLUMNS),
    sql.SQL(",").join(map(sql.Identifier, COLUMNS)))
DATES = ("tanggal_lahir", "tanggal_pernikahan")


def load_keys(manifest, concurrency, database="baseline_100k"):
    """One fixed corpus retained outside repo for later plain/protected comparisons."""
    if database not in BASELINE_ROWS:
        raise ValueError("Key corpus database not authorized")
    path = private_directory() / (database + "_keys_v1.json")
    if not path.exists():
        rng = random.Random(manifest["seed"])
        with psycopg.connect(**parameters(database), row_factory=dict_row) as conn:
            identifiers = [r["id"] for r in conn.execute("SELECT id FROM public.anggota ORDER BY id")]
            chosen = rng.sample(identifiers[:-1], min(manifest["key_pool"] - 1, len(identifiers) - 1)) + [identifiers[-1]]
            source = conn.execute(SELECT + sql.SQL("WHERE id = ANY(%s) ORDER BY id"), (chosen,)).fetchall()
            pages = []
            anchors = rng.sample(range(0, len(identifiers), manifest["page_size"]), manifest["page_pool"])
            for anchor in anchors:
                rows = conn.execute("SELECT id,nama,jenis_kelamin FROM public.anggota WHERE id>%s ORDER BY id LIMIT %s",
                                    (anchor, manifest["page_size"])).fetchall()
                pages.append({"anchor": anchor, "rows": [list(r.values()) for r in rows]})
            templates = None
            for attempt in range(50):
                candidates = list(generate(source, len(source) + concurrency, manifest["seed"] + attempt))[len(source):]
                collision = False
                for col in UNIQUE:
                    values = [r[col] for r in candidates]
                    if conn.execute(sql.SQL("SELECT EXISTS (SELECT 1 FROM public.anggota WHERE {} = ANY(%s))").format(
                            sql.Identifier(col)), (values,)).fetchone()["exists"]:
                        collision = True
                        break
                if not collision:
                    templates = candidates
                    break
            if templates is None:
                raise ValueError("Synthetic insert namespace collision")
        payload = {"version": 1, "database": database, "seed": manifest["seed"], "concurrency": concurrency,
                   "profiles": source, "pages": pages, "insert_templates": templates}
        with path.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, default=str, ensure_ascii=False)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (payload["seed"] != manifest["seed"] or payload["concurrency"] != concurrency
            or payload.get("database", "baseline_100k") != database):
        raise ValueError("Existing key corpus parameters differ")
    for row in payload["profiles"] + payload["insert_templates"]:
        for col in DATES:
            row[col] = date.fromisoformat(row[col]) if row[col] is not None else None
    return payload, {"version": 1, "seed": payload["seed"], "sha256": file_hash(path),
                     "profile_count": len(payload["profiles"]), "page_count": len(payload["pages"]),
                     "location": "DPR_PRIVATE_DIR/benchmark (not exported)"}


class PlaintextAdapter:
    def __init__(self, keys, database="baseline_100k"):
        self.keys = keys
        self.database = database

    def connect(self):
        return psycopg.connect(**parameters(self.database), autocommit=True, prepare_threshold=5)

    def execute(self, conn, operation, index, worker):
        row = self.keys["profiles"][index % len(self.keys["profiles"])]
        expected = tuple(row[c] for c in COLUMNS)
        if operation in {"read_by_nik", "read_by_email", "read_profile"}:
            col = {"read_by_nik": "no_ktp", "read_by_email": "email", "read_profile": "id"}[operation]
            actual = conn.execute(SELECT + sql.SQL("WHERE {}=%s").format(sql.Identifier(col)), (row[col],)).fetchall()
            ok = actual == [expected]
        elif operation == "list_page":
            page = self.keys["pages"][index % len(self.keys["pages"])]
            actual = conn.execute("SELECT id,nama,jenis_kelamin FROM public.anggota WHERE id>%s ORDER BY id LIMIT %s",
                                  (page["anchor"], 50)).fetchall()
            ok = actual == [tuple(r) for r in page["rows"]]
        elif operation == "update_contact":
            contact = self.keys["insert_templates"][worker]["handphone"]
            with conn.transaction(force_rollback=True):
                actual = conn.execute("UPDATE public.anggota SET handphone=%s WHERE id=%s RETURNING id,handphone",
                                      (contact, row["id"])).fetchone()
                ok = actual == (row["id"], contact)
        elif operation == "insert_member":
            template = dict(self.keys["insert_templates"][worker], id=-(worker + 1))
            expected = tuple(template[c] for c in COLUMNS)
            with conn.transaction(force_rollback=True):
                actual = conn.execute(INSERT, expected).fetchone()
                ok = actual == expected
        else:
            raise ValueError("Unknown business operation")
        if not ok:
            raise ValueError("Business result mismatch (values withheld)")
