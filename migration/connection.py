"""Require the decided pg-dpr endpoint/TLS and fence off original/baseline targets."""

import json
import os
from pathlib import Path


TARGETS = json.loads((Path(__file__).resolve().parents[1] / "infra/database-targets.json").read_text())


def connection_parameters(database: str, *, source: bool = False) -> dict:
    allowed = TARGETS["read_only_sources"] if source else TARGETS["protected_databases"]
    if database not in allowed:
        raise ValueError("Database is not an allowed migration source/target")
    if os.environ.get("PGPORT", "5433") != "5433":
        raise ValueError("The project database must use published port 5433")
    ca = os.environ.get("PGSSLROOTCERT", "")
    if not ca or not Path(ca).is_file() or not os.environ.get("PGUSER") or not os.environ.get("PGPASSWORD"):
        raise ValueError("PGUSER, PGPASSWORD and a trusted PGSSLROOTCERT are required")
    params = {"host": os.environ.get("PGHOST", TARGETS["host"]), "port": TARGETS["port"],
              "dbname": database, "user": os.environ["PGUSER"], "password": os.environ["PGPASSWORD"],
              "sslmode": "verify-full", "sslrootcert": ca, "gssencmode": "disable", "connect_timeout": 5}
    if source:
        params["options"] = "-c default_transaction_read_only=on"
    return params
