"""Public launcher. setup uses only Python's standard library."""
import argparse
import json
import os
from pathlib import Path
import sys

from .bootstrap import ROOT, setup, test


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("setup", "demo", "verify", "test"))
    parser.add_argument("--data", type=Path, default=os.environ.get("DPR_DEMO_DATA", str(ROOT / "sql/baseline/02_data.sql")))
    parser.add_argument("--native-pg-bin", type=Path)
    parser.add_argument("--native-bao-bin", type=Path)
    parser.add_argument("--demo-seconds", type=int, help="Optional bounded demo lifetime for automated smoke checks")
    args = parser.parse_args(argv)
    if args.demo_seconds is not None and not 1 <= args.demo_seconds <= 86400:
        parser.error("--demo-seconds must be 1..86400")
    if sys.version_info < (3, 11):
        parser.error("Python 3.11+ required")
    try:
        if args.command == "setup":
            setup()
        elif args.command == "test":
            return test()
        else:
            # The initial interpreter may not have the project dependencies.
            from .bootstrap import python_bin
            runtime = python_bin(ROOT / ".venv")
            if not runtime.is_file():
                raise RuntimeError("Run python -m infra.reproduce setup first")
            if Path(sys.executable).resolve() != runtime.resolve():
                import subprocess
                return subprocess.call([str(runtime), "-m", "infra.reproduce", *(sys.argv[1:] if argv is None else argv)], cwd=ROOT)
            from .workflow import run
            return run(args)
    except (Exception, KeyboardInterrupt) as error:
        print(json.dumps({"passed": False, "error_type": type(error).__name__,
                          "details": "withheld; check prerequisites and evidence/reproduction/; no secrets printed"}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
