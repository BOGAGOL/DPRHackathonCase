"""Aggregate exposure accounting. Missing populations are never counted as zero."""
import argparse
import json
from pathlib import Path

from benchmark.common import ROOT, file_hash, utc_now, write_csv, write_json
from .known_values import KnownValues
from .profile import DIRECT, FIN, PII, SENSITIVE


def ratio(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "ratio": numerator / denominator if denominator else None}


def build_report(known, leak, residual):
    if not leak["full_artifact_equals_known_baseline"]:
        raise ValueError("Baseline ELS requires verified whole-artifact equality")
    if known.meta["baseline_checksum_sha256"] != leak["known_values_baseline_checksum_sha256"]:
        raise ValueError("Known ledger and artifact evidence refer to different baselines")
    populations = {}
    for group, denominator in leak["population_rows"].items():
        recovered = leak["populations"][group]
        cells = leak["denominators"][group]
        populations[group] = {
            "ESCE": ratio(sum(recovered["exposed_cells"].values()), sum(cells.values())),
            "DIE": ratio(recovered["direct_exposed_rows"], denominator),
            "columns": [{"column": c, **ratio(recovered["exposed_cells"].get(c, 0), cells.get(c, 0))} for c in SENSITIVE]}
    return {"status": "PASSED", "measurement_only": True, "scenario": "baseline_dump", "dataset": "baseline_1m",
            "timestamp_utc": utc_now(), "code_commit": leak["code_commit"], "worktree_code_sha256": leak["worktree_code_sha256"],
            "budget_code_sha256": file_hash(Path(__file__)),
            "targets_commit": leak["targets_commit"], "artifact_sha256": leak["artifact_sha256"],
            "ESCE_scope": "25 future AEAD columns per CONTRACT section 3; REF four and surrogate id excluded; not the independent scanner taxonomy",
            "direct_identifiers": list(DIRECT), "populations": populations,
            "ELS": {"deterministic_bidx_columns": [], "bidx_count": 0,
                    "plaintext_equality_column_count": 29,
                    "sqlite_temp_store": known.connection.execute("PRAGMA temp_store").fetchone()[0],
                    "method": "exact SQLite GROUP BY on private known ledger after every artifact row matched; NULL excluded and separately reported",
                    "columns": known.equality()},
            "DBR": {"credentials_needed": "none", "domains_exposed": {"PII": list(PII), "FIN": list(FIN)},
                    "meaning": "Baseline plaintext exposure, not a tested OpenBao key compromise"},
            "residual": {"file": "evidence/leakage/residual_before.json", "attributes": residual["attributes"],
                         "combinations_per_population": len(residual["populations"]["all"]["combinations"])},
            "before_after": {"before": "measured", "after": "BELUM DIUJI; requires Module A artifact/profile and applicable credentials"},
            "target_status": {"S03": "BELUM DIUJI: target applies to protected dump without keys"},
            "limitations": ["Logical snapshot only; no physical files/WAL/operational log claim.",
                            "ESCE uses exact linked cells, not substring occurrence or merely possible inference.",
                            "DIE is this frozen direct-identifier list, not all possible re-identification attacks."]}


def summary_rows(budget, residual):
    rows = []
    for population, values in budget["populations"].items():
        for name in ("ESCE", "DIE"):
            metric = values[name]
            rows.append({"population": population, "metric": name, "before": metric["ratio"],
                         "numerator": metric["numerator"], "denominator": metric["denominator"], "after": "BELUM DIUJI"})
        combinations = residual["populations"][population]["combinations"]
        rows.append({"population": population, "metric": "residual_min_k_across_1_to_3_attributes",
                     "before": min(r["k_min"] for r in combinations), "numerator": "", "denominator": "", "after": "BELUM DIUJI"})
        birth = residual["populations"][population]["birth_reference"]
        rows.append({"population": population, "metric": "birth_reference_unique_ratio", "before": birth["unique_ratio"],
                     "numerator": birth["unique_rows"], "denominator": birth["total_rows"], "after": "BELUM DIUJI"})
    for name, value in (("ELS_plaintext_equality_columns", budget["ELS"]["plaintext_equality_column_count"]),
                        ("ELS_bidx_columns", budget["ELS"]["bidx_count"])):
        rows.append({"population": "all", "metric": name, "before": value,
                     "numerator": "", "denominator": "", "after": "BELUM DIUJI"})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--known-values", type=Path, required=True)
    parser.add_argument("--leak", type=Path, default=ROOT / "evidence/leak/baseline_dump.json")
    parser.add_argument("--residual", type=Path, default=ROOT / "evidence/leakage/residual_before.json")
    args = parser.parse_args()
    known = KnownValues(args.known_values)
    try:
        residual = json.loads(args.residual.read_text(encoding="utf-8"))
        report = build_report(known, json.loads(args.leak.read_text(encoding="utf-8")), residual)
        write_json(ROOT / "evidence/leakage/baseline_dump.json", report)
        write_csv(ROOT / "evidence/leakage/before_after.csv", summary_rows(report, residual))
    finally:
        known.close()


if __name__ == "__main__":
    main()
