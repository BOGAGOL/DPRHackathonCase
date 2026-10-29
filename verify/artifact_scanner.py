"""Run the existing scanner engine on the same artifact's bounded reservoir."""
import yaml

from benchmark.common import ROOT
from datagen.model import COLUMNS
from scanner.model import Table
from scanner.priority import load_type_policy
from scanner.reporting import analyze, emit


def scan_reservoir(rows, total, artifact_sha256, anonymity, duration, out):
    config = yaml.safe_load((ROOT / "scanner/config/weights.yaml").read_text(encoding="utf-8"))
    config["type_policy"] = load_type_policy()
    environment = yaml.safe_load((ROOT / "scanner/config/environment_before.yaml").read_text())
    types = ["bigint" if c == "id" else "date" if c in ("tanggal_lahir", "tanggal_pernikahan") else
             "smallint" if c in ("jumlah_anak", "jumlah_jiwa", "jumlah_tanggungan") else "character varying" for c in COLUMNS]
    table = Table("public.anggota", list(COLUMNS), types, rows, total)
    inventory, features, relations = analyze([table], config, environment)
    relations["foreign_keys"] = []
    relations["foreign_keys_scope"] = "not read from data-only logical dump"
    output = [{"table": "public.anggota", **row, "scope": "full_artifact_aggregate"} for row in anonymity]
    return emit(out, inventory, features, relations, output, label="before", source={
        "mode": "dump", "artifact": "DPR_PRIVATE_DIR/baseline_1m.dump", "artifact_sha256": artifact_sha256,
        "preprocessing": "pg_restore data-only stdout; non-executing streaming text COPY",
        "sampling": "uniform reservoir seed=42 over all rows of same artifact; scanner engine v1.2",
        "k_anonymity": "full-artifact REF + virtual age_band + variable NULL indicators; see residual_before.json",
        "table_counts": {"public.anggota": total}}, sample=1000, duration=duration)
