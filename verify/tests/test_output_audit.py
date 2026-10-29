import json

from verify.output_audit import TextFields, audit, strings


def test_fields_and_recursive_strings():
    assert set(strings({"a": ["literal", None, 1, {"nested": "other"}]})) == {"literal", "other"}
    parser = TextFields()
    parser.feed("<td>fixture &amp; value</td>")
    assert "fixture & value" in parser.fields


def test_exact_field_audit_rejects_unmasked_value(tmp_path):
    from unittest.mock import MagicMock
    from verify.profile import SENSITIVE
    known = MagicMock()
    row = [None] * len(SENSITIVE)
    row[SENSITIVE.index("nama")] = "fixture-person-only"
    known.connection.execute.return_value = [row]
    path = tmp_path / "result.json"
    path.write_text(json.dumps({"masked": "fi***"}))
    assert audit(known, [path])["status"] == "PASSED"
    path.write_text(json.dumps({"unmasked": "fixture-person-only"}))
    report = audit(known, [path])
    assert report["status"] == "FAILED"
    assert report["exact_unmasked_field_matches_by_column"] == {"nama": 1}
    assert "fixture-person-only" not in json.dumps(report)
    path.write_text("column\nfixture-person-only\n")
    csv = path.with_suffix(".csv")
    path.rename(csv)
    assert audit(known, [csv])["status"] == "FAILED"
    html = path.with_suffix(".html")
    html.write_text("<td>fixture-person-only</td>")
    assert audit(known, [html])["status"] == "FAILED"


def test_public_reference_date_exception_is_only_one_named_field(tmp_path):
    from unittest.mock import MagicMock
    from verify.profile import SENSITIVE
    known = MagicMock()
    row = [None] * len(SENSITIVE)
    row[SENSITIVE.index("tanggal_pernikahan")] = "2026-10-01"
    known.connection.execute.return_value = [row]
    path = tmp_path / "residual_before.json"
    payload = {"age_band": {"reference_date": "2026-10-01"}}
    path.write_text(json.dumps(payload))
    report = audit(known, [path])
    assert report["status"] == "PASSED" and len(report["public_metadata_exceptions"]) == 1
    payload["unmasked_personal_sample"] = "2026-10-01"
    path.write_text(json.dumps(payload))
    assert audit(known, [path])["status"] == "FAILED"
