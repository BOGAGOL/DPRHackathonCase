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
    baseline = evidence_status(APP / "evidence/access-control/baseline-100k.json")
    checks = baseline.get("checks", {})
    # A stale arbitrary PASS or policy test double must not certify this target.
    required = {"datagen_validation", "baseline_checksum_before", "baseline_checksum_restored",
                "source_checksum_unchanged", "pg18", "non_tls_rejected", "wrong_ca_rejected",
                "last_page_100k", "insert", "patch", "patch_restore", "A5_total_unavailable", "A5_threshold", "A5_released_group",
                "forced_rls_member_scope", "live_browser_probe_passed", "idor_detail", "idor_patch"}
    baseline_passed = (baseline.get("status") == "PASSED" and isinstance(checks, dict)
                       and required.issubset(checks) and all(v is True for v in checks.values()))
    protected = evidence_status(APP / "evidence/access-control/protected-integration.json")
    protected_checks = protected.get("checks", {})
    protected_required = {"B_provisioning_with_A_schema", "A_schema_owner_preserved", "A_audit_no_extra_grants",
                          "A_ciphertext_decrypts_in_B", "scoped_insert_no_RETURNING", "new_record_scope_trigger",
                          "reencrypt_and_bidx_update", "real_AAD_swap_generic_500", "A_audit_context_and_error",
                          "cohort_filter_rejected", "B4_small_label_omitted", "A5_total_unavailable",
                          "A5_threshold", "A5_released_group", "live_api_https_verified_ca", "live_web_https_verified_ca",
                          "live_browser_probe_passed", "revoked_key_identity_fails_closed"}
    protected_passed = (protected.get("status") == "PASSED" and isinstance(protected_checks, dict)
                        and protected_required.issubset(protected_checks)
                        and all(v is True for v in protected_checks.values()))
    return {"module": "B", "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            "implementation": {"plain": "IMPLEMENTED", "protected_adapter": "IMPLEMENTED", "crypto_implementation_owner": "Module A"},
            "external_dependencies": dependencies,
            "evidence": {"backend": evidence_status(APP / "evidence/access-control/unit-tests.json"),
                         "browser": evidence_status(APP / "evidence/access-control/browser-tests.json"),
                         "postgres_tls": evidence_status(APP / "evidence/access-control/postgres-tls.json"),
                         "baseline_100k": baseline, "protected_disposable": protected},
            "target_integration": {"team_baseline_100k": "PASSED: Zhafif local pg-dpr, team schema/dataset + C datagen seed42, verified TLS and six-role HTTPS flow" if baseline_passed else "NOT TESTED: complete local baseline_100k evidence unavailable",
                                   "live_protected": "PASSED: disposable PG18/OpenBao TLS with actual Module A schema/toolkit and six-role HTTPS flow" if protected_passed else "NOT TESTED: complete actual Module A protected integration evidence unavailable",
                                   "migrated_protected_datasets": "NOT TESTED: local protected_734/100k/1m not provisioned; disposable checks do not certify migrated datasets",
                                   "api_benchmark": "NOT TESTED: measured by Module C on target datasets"},
            "status": "PARTIAL: migrated protected datasets and official API benchmark remain NOT TESTED"}


def main():
    target = APP / "evidence/access-control/readiness.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    value = report()
    target.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": value["status"], "external_dependencies": value["external_dependencies"]}))


if __name__ == "__main__":
    main()
