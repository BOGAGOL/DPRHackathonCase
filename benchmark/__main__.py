"""python -m benchmark {run,backup-restore}; no credentials or driver errors printed."""

import argparse
import json
from pathlib import Path
import sys

from .backup_restore import backup_restore
from .common import EVIDENCE, session_paths, utc_now, write_json
from .runner import baseline_run


def main(argv=None):
    parser = argparse.ArgumentParser(description="Initial DB plaintext baseline on pg-dpr")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--db", choices=["baseline_100k", "baseline_1m"], default="baseline_100k")
    run.add_argument("--label", choices=["before"], default="before")
    run.add_argument("--adapter", choices=["plain"], default="plain")
    run.add_argument("--scenario", default="all")
    run.add_argument("--runs", type=int, default=3)
    run.add_argument("--duration", type=float, default=60)
    run.add_argument("--concurrency", type=int, default=8)
    run.add_argument("--warmup", type=float, default=10)
    backup = sub.add_parser("backup-restore")
    backup.add_argument("--db", choices=["baseline_100k", "baseline_1m"], default="baseline_100k")
    backup.add_argument("--label", choices=["before"], default="before")
    backup.add_argument("--runs", type=int, default=3)
    backup.add_argument("--keep", action="store_true")
    compare = sub.add_parser("compare")
    compare.add_argument("--before", type=Path, required=True)
    compare.add_argument("--after", type=Path, required=True)
    compare.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "compare":
            from .compare import main as compare_main
            compare_main(["--before", str(args.before), "--after", str(args.after), "--out", str(args.out)])
            return 0
        if args.command == "run":
            result = baseline_run(args.runs, args.duration, args.concurrency, args.warmup, args.scenario, database=args.db)
        else:
            result = backup_restore(args.runs, args.keep, database=args.db)
        print(json.dumps({"status": result["status"], "command": args.command}), flush=True)
        return 0 if result["status"] == "PASSED" else 1
    except Exception:
        if args.command == "compare":
            write_json(args.out / "failure.json", {"status": "FAILED", "command": "compare",
                       "timestamp_utc": utc_now(), "details": "Invalid comparison input; private details withheld"})
            print("Comparison failed; details withheld.", file=sys.stderr)
            return 2
        evidence = EVIDENCE if args.db == "baseline_100k" else session_paths(args.db)[1]
        write_json(evidence / "failure.json", {"status": "FAILED", "command": args.command,
                   "timestamp_utc": utc_now(), "details": "Credentials, SQL, row values and driver diagnostics withheld; raw retained"})
        print("Benchmark failed; private values and driver details withheld. Inspect aggregate evidence.", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
