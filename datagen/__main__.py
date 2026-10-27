"""PowerShell-compatible CLI; public errors intentionally withhold driver details."""

import argparse
import json
from pathlib import Path
import sys

from .database import ROOT, build, provision, record, snapshot, validate_database


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create a NEW deterministic baseline, never overwrite source")
    parser.add_argument("action", nargs="?", choices=("generate", "validate", "snapshot", "provision"), default="generate")
    parser.add_argument("--target-db", "--db", dest="database", default="baseline_100k")
    parser.add_argument("--rows", type=int, default=100000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--replicate-anomalies", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == "snapshot":
            if args.out is None:
                raise ValueError("--out required")
            result = snapshot(args.database, args.out)
        elif args.action == "provision":
            result = provision(args.database)
        elif args.action == "validate":
            result = validate_database(args.database, args.rows, args.replicate_anomalies)
            path = ROOT / "evidence/datasets" / (args.database + ".json")
            payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"database": args.database}
            result["matches_recorded_baseline"] = result["checksum_sha256"] == payload.get(
                "baseline_checksum_sha256", result["checksum_sha256"])
            result["source_database_unchanged"] = result["source_checksum_sha256"] == payload.get(
                "validation", {}).get("source_checksum_sha256", result["source_checksum_sha256"])
            result["passed"] = result["passed"] and result["matches_recorded_baseline"] and result["source_database_unchanged"]
            payload.update(validation=result, status="PASSED" if result["passed"] else "FAILED")
            record(args.database, payload)
            if not result["passed"]:
                raise ValueError("Validation failed")
        else:
            result = build(args.database, args.rows, args.seed, args.replicate_anomalies)
    except Exception:
        print("Datagen failed; credentials, SQL details and row values withheld. Check env/target/evidence.", file=sys.stderr)
        return 2
    print(json.dumps({"status": "PASSED", "action": args.action, "database": args.database}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
