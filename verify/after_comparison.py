"""Compare measured artifact budgets at matching scales without discarding before evidence."""

import csv
import json
from pathlib import Path
import shutil

from benchmark.common import ROOT, write_csv, write_json, utc_now
from .protected_artifact import SCENARIOS


def comparison_rows(before, after, before_residual, after_residual):
    rows = []
    for scope in ("all", "source_734", "synthetic"):
        for metric in ("ESCE", "DIE"):
            observed = after["populations"][scope][metric]
            rows.append({"dataset": after["dataset"], "scenario": after["scenario"], "population": scope,
                         "metric": metric, "before": before["populations"][scope][metric]["ratio"], "after": observed["ratio"],
                         "numerator": observed["numerator"], "denominator": observed["denominator"]})
        low_before = min(c["k_min"] for c in before_residual["populations"][scope]["combinations"])
        low_after = min(c["k_min"] for c in after_residual["populations"][scope]["combinations"])
        rows.append({"dataset": after["dataset"], "scenario": after["scenario"], "population": scope,
                     "metric": "residual_min_k_across_1_to_3_plaintext_attributes", "before": low_before,
                     "after": low_after, "numerator": "", "denominator": ""})
    for metric, key in (("ELS_bidx_columns", "bidx_count"), ("ELS_plaintext_equality_columns", "plaintext_equality_column_count")):
        rows.append({"dataset": after["dataset"], "scenario": after["scenario"], "population": "all", "metric": metric,
                     "before": before["ELS"][key], "after": after["ELS"][key], "numerator": "", "denominator": ""})
    return rows


def run(root=ROOT):
    root = Path(root)
    rows, scenarios = [], []
    for scale in ("100k", "1m"):
        folder = root / "evidence/leakage"
        before_path = folder / "baseline_100k/baseline_dump.json" if scale == "100k" else folder / "baseline_dump.json"
        residual_path = folder / "baseline_100k/residual_before.json" if scale == "100k" else folder / "residual_before.json"
        before = json.loads(before_path.read_text())
        before_residual = json.loads(residual_path.read_text())
        target = folder / ("protected_" + scale)
        after_residual = json.loads((target / "residual_after.json").read_text())
        if before["status"] != "PASSED" or after_residual["status"] != "PASSED":
            raise ValueError("Incomplete before/after residual evidence")
        for scenario in SCENARIOS:
            after = json.loads((target / (scenario + ".json")).read_text())
            if after["status"] != "PASSED":
                raise ValueError("Incomplete after leakage evidence")
            rows.extend(comparison_rows(before, after, before_residual, after_residual))
            scenarios.append({"dataset": after["dataset"], "scenario": scenario,
                "ESCE": after["populations"]["all"]["ESCE"], "DIE": after["populations"]["all"]["DIE"],
                "DBR": after["DBR"]})
    destination = root / "evidence/leakage/before_after.csv"
    if destination.exists():
        archive = destination.parent / "history/before_after_before_protected_20261028.csv"
        archive.parent.mkdir(exist_ok=True)
        if not archive.exists():
            shutil.copyfile(destination, archive)
    write_csv(destination, rows)
    report = {"schema_version": 1, "status": "PASSED", "timestamp_utc": utc_now(), "scenarios": scenarios,
              "comparison_rows": len(rows), "official_benchmark_executed": False}
    write_json(root / "evidence/leakage/after_summary.json", report)
    return report


if __name__ == "__main__":
    run()
