"""Independent ratio and absolute latency targets; input summaries contain no row values."""

import argparse
import json
from pathlib import Path

from .common import write_csv, write_json


def compare_metrics(before, after, scenario):
    write = scenario in {"update_contact", "insert_member", "mixed"}
    if scenario not in {"read_by_nik", "read_by_email", "read_profile", "list_page", "update_contact", "insert_member", "mixed"}:
        raise ValueError("Unknown scenario")
    if before["p95_ms"] <= 0 or before["throughput_rps"] <= 0:
        raise ValueError("Invalid baseline metrics")
    delta = after["p95_ms"] - before["p95_ms"]
    ratio = after["p95_ms"] / before["p95_ms"]
    return {"scenario": scenario, "p50_delta_ms": after["p50_ms"] - before["p50_ms"],
            "p95_delta_ms": delta, "p95_ratio": ratio,
            "p95_absolute_allowance_ms": 10 if write else 5,
            "P01_ratio_passed": ratio <= 1.5, "P01_absolute_passed": delta <= (10 if write else 5),
            "throughput_ratio": after["throughput_rps"] / before["throughput_rps"],
            "P02_passed": after["throughput_rps"] >= .7 * before["throughput_rps"],
            "P03_passed": after["error_rate"] <= before["error_rate"],
            "before_db_time": before.get("db_time"), "after_db_time": after.get("db_time")}


def compare_reports(before, after, out):
    rows = [compare_metrics(before[s], after[s], s) for s in before]
    write_json(out / "comparison.json", {"scenarios": rows, "ratio_and_absolute_evaluated_separately": True})
    write_csv(out / "comparison.csv", [{k: v for k, v in r.items() if k not in {"before_db_time", "after_db_time"}} for r in rows])
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    summaries = []
    for path in (args.before, args.after):
        payload = json.loads((path / "summary.json" if path.is_dir() else path).read_text(encoding="utf-8"))
        summaries.append({r["scenario"]: r for r in payload["median_between_runs"]})
    compare_reports(*summaries, args.out)


if __name__ == "__main__":
    main()
