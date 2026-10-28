"""Historical pre-A5 passes cannot certify the new analytics contract."""
import importlib.util
import json
from pathlib import Path
import pytest


@pytest.mark.parametrize("include_a5", [False, True])
def test_readiness_requires_a5_acceptance(tmp_path, monkeypatch, include_a5):
    path = Path(__file__).resolve().parents[1] / "scripts/check_ready.py"
    spec = importlib.util.spec_from_file_location("readiness_a5_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "APP", tmp_path)
    output = tmp_path / "evidence/access-control"
    output.mkdir(parents=True)
    baseline = set("datagen_validation baseline_checksum_before baseline_checksum_restored source_checksum_unchanged pg18 non_tls_rejected wrong_ca_rejected last_page_100k insert patch patch_restore aggregate_count forced_rls_member_scope live_browser_probe_passed idor_detail idor_patch".split())
    protected = set("B_provisioning_with_A_schema A_schema_owner_preserved A_audit_no_extra_grants A_ciphertext_decrypts_in_B scoped_insert_no_RETURNING new_record_scope_trigger reencrypt_and_bidx_update real_AAD_swap_generic_500 A_audit_context_and_error filtered_count_suppressed live_api_https_verified_ca live_web_https_verified_ca live_browser_probe_passed revoked_key_identity_fails_closed".split())
    if include_a5:
        baseline.update({"A5_total_unavailable", "A5_threshold", "A5_released_group"})
        protected.update({"A5_total_unavailable", "A5_threshold", "A5_released_group", "B4_small_label_omitted", "cohort_filter_rejected"})
    for filename, checks in [("baseline-100k.json", baseline), ("protected-integration.json", protected)]:
        (output / filename).write_text(json.dumps({"status": "PASSED", "checks": dict.fromkeys(checks, True)}), encoding="utf-8")
    report = module.report()
    for target in ("team_baseline_100k", "live_protected"):
        assert report["target_integration"][target].startswith("PASSED" if include_a5 else "NOT TESTED")
