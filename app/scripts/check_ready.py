"""Combine independently labelled evidence. Missing external dependencies never count as PASS."""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app"


def evidence_status(path):
    # Missing/invalid inputs are distinct; never copy parser errors or file contents to output.
    try:
        path = Path(path)
        if not path.exists():
            return {"status": "NOT TESTED"}
        if not path.is_file():
            return {"status": "INVALID EVIDENCE"}
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError, TypeError):
        return {"status": "INVALID EVIDENCE"}
    statuses = {"PASSED", "FAILED", "NOT TESTED", "PARTIAL", "BLOCKED", "TESTED", "INVALID EVIDENCE"}
    if not isinstance(value, dict) or not isinstance(value.get("status"), str) or value["status"] not in statuses:
        return {"status": "INVALID EVIDENCE"}
    return {k: value[k] for k in ["status", "total", "counts", "passed", "failed", "skipped", "checks", "summary", "scope"] if k in value}


def report():
    dependencies = {"toolkit_package": (ROOT / "toolkit/dprcrypto").is_dir(),
                    "protection_profile": (ROOT / "policy/protection_profile.yaml").is_file(),
                    "shared_test_vectors": (ROOT / "docs/contracts/test_vectors.json").is_file()}
    return {"module": "B", "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            "implementation": {"plain": "IMPLEMENTED", "protected_adapter": "IMPLEMENTED", "crypto_implementation_owner": "Module A"},
            "external_dependencies": dependencies,
            "evidence": {"backend": evidence_status(APP / "evidence/access-control/unit-tests.json"),
                         "browser": evidence_status(APP / "evidence/access-control/browser-tests.json"),
                         "postgres_tls": evidence_status(APP / "evidence/access-control/postgres-tls.json")},
            "target_integration": {"team_baseline_100k": "NOT TESTED: target container/credentials unavailable on current host",
                                   "live_protected": "NOT TESTED: requires Module A toolkit/schema/profile/vectors and OpenBao",
                                   "api_benchmark": "NOT TESTED: measured by Module C on target datasets"},
            "status": "PARTIAL: local implementation verified separately; target integrations remain NOT TESTED"}


def main():
    target = APP / "evidence/access-control/readiness.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    value = report()
    target.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": value["status"], "external_dependencies": value["external_dependencies"]}))


if __name__ == "__main__":
    main()
