"""Shared, reviewed database allowlist; row-count expectations are independent."""

import json
from pathlib import Path


TARGETS = json.loads((Path(__file__).parent/"database-targets.json").read_text(encoding="utf-8"))
MIGRATION_DATASETS = TARGETS["migration_pairs"]
MIGRATION_PAIRS = {source:definition["target"] for source,definition in MIGRATION_DATASETS.items()}
PROTECTED_DATABASES = tuple(TARGETS["protected_databases"])
READ_ONLY_SOURCES = tuple(TARGETS["read_only_sources"])
