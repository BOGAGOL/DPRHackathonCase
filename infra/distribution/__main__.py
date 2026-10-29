"""python -m infra.distribution {sbom,check,build}; emits sanitized JSON reports."""

import argparse
import json
from pathlib import Path

from infra.security import REPO
from . import package, sbom


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("sbom", "check", "build"))
    parser.add_argument("--output", type=Path, default=REPO / "dist/source")
    args = parser.parse_args(argv)
    try:
        if args.command == "sbom":
            report = {"passed": True, **sbom.generate(REPO)}
        elif args.command == "check":
            report = package.check(REPO)
        else:
            report = package.build(REPO, args.output)
    except Exception as error:
        report = {
            "passed": False,
            "error_type": type(error).__name__,
            "details": "withheld; no private values printed",
        }
    path = REPO / "evidence/distribution/generated" / (args.command + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "report": str(path),
                "status": report.get("status"),
            }
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
