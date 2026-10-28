"""Export only statuses/counts/timing from local pytest JUnit, never failure payloads."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

APP = Path(__file__).resolve().parents[1]


def summarize(junit):
    root = ET.parse(junit).getroot()
    records = []
    for case in root.iter("testcase"):
        state = ("FAILED" if case.find("failure") is not None or case.find("error") is not None else
                 "SKIPPED" if case.find("skipped") is not None else "PASSED")
        records.append({"test": case.get("name"), "suite": case.get("classname"),
                        "status": state, "seconds": float(case.get("time", "0"))})
    counts = {state.lower(): sum(r["status"] == state for r in records) for state in ["PASSED", "FAILED", "SKIPPED"]}
    return {"status": "PASSED" if records and counts["failed"] == 0 else "FAILED", "total": len(records),
            "counts": counts, "cases": records}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit", type=Path, default=APP / ".local/security-tests.xml")
    parser.add_argument("--output", type=Path, default=APP / "evidence/access-control/unit-tests.json")
    args = parser.parse_args()
    result = summarize(args.junit)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=APP.parent, capture_output=True, text=True, check=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "app"], cwd=APP.parent,
                                capture_output=True, text=True, check=True).stdout.strip())
    snapshot = hashlib.sha256()
    for directory, subdirectories, files in os.walk(APP):
        subdirectories[:] = sorted(d for d in subdirectories if d not in {"node_modules", ".next", ".local", ".venv", ".git", "__pycache__", ".pytest_cache", "evidence", "app"})
        for filename in sorted(files):
            path = Path(directory) / filename
            if filename.startswith(".env") or path.suffix in {".key", ".crt", ".log", ".pyc", ".tsbuildinfo"}:
                continue
            snapshot.update(path.relative_to(APP).as_posix().encode() + b"\0" + path.read_bytes())
    result.update(checked_at_utc=datetime.now(timezone.utc).isoformat(), source_commit=commit,
                  app_worktree_dirty=dirty, app_source_sha256_at_export=snapshot.hexdigest(),
                  command="python -m pytest -c app/pytest.ini app/tests -q --junitxml=app/.local/security-tests.xml",
                  scope="Isolated invented SQLite fixtures; protected policy uses opaque-reference test double; shared Module A vectors additionally verified when installed",
                  not_tested=["Live PostgreSQL/OpenBao integration (reported separately)", "Live baseline_100k or migrated datasets (reported separately)", "Browser XSS and transport TLS (reported separately)"],
                  skipped_scope="Plain-mode ciphertext-swap test is not applicable; protected-mode swap is exercised",
                  privacy="No failure messages, request bodies, response values, cookies, credentials or crypto material exported")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "total": result["total"], "counts": result["counts"]}))


if __name__ == "__main__":
    main()
