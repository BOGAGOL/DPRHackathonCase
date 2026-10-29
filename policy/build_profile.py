"""Deterministic assessment -> team overrides -> contract-checked v1 protection profile."""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
NORMALIZATION = {"no_ktp": "ascii_digits_preserve_leading_zero", "email": "strip_lower", "pengguna": "strip_case_sensitive"}


def text_hashes(path: Path) -> tuple[str, ...]:
    """Equivalent UTF-8 text identities across Git LF/CRLF checkouts, canonical LF first."""
    raw = path.read_bytes()
    lf = raw.replace(b"\r\n",b"\n")
    return tuple(dict.fromkeys(hashlib.sha256(value).hexdigest() for value in (lf,lf.replace(b"\n",b"\r\n"),raw)))


def contract_columns(path: Path) -> dict:
    section = path.read_text(encoding="utf-8-sig").split("## 3.", 1)[1].split("## 4.", 1)[0]
    columns = {}
    for line in section.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not line.startswith("|") or len(cells) != 5 or cells[2] not in ("AEAD", "plaintext (REF)"):
            continue
        for name in cells[0].split(","):
            column = name.strip()
            columns[column] = {"domain": cells[1] if cells[1] in ("PII", "FIN") else None,
                "aead": cells[2] == "AEAD", "bidx": cells[3] != "-"}
    if len(columns) != 29 or sum(item["aead"] for item in columns.values()) != 25:
        raise ValueError("Unrecognized protection contract")
    return columns


def load_inventory(path: Path, expected: set[str]) -> dict:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"table", "column", "detected_type", "risk_level", "recommendation", "triage", "confidence", "priority_score"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("Scanner inventory headers missing")
        rows = {}
        for row in reader:
            if row["table"] != "public.anggota":
                continue
            column = row["column"]
            if column in rows or column not in expected | {"id"}:
                raise ValueError("Duplicate or unexpected source column")
            rows[column] = row
    if set(rows) - {"id"} != expected:
        raise ValueError("Scanner inventory does not cover every contract column")
    return rows


def assessment(row: dict) -> dict:
    confidence, priority = float(row["confidence"]), float(row["priority_score"])
    if not math.isfinite(confidence) or not 0 <= confidence <= 100 or not math.isfinite(priority) or priority < 0:
        raise ValueError("Invalid scanner score")
    actions = row["recommendation"].split("+")
    if not actions or any(action not in {"encrypt", "blind_index", "mask", "retain", "delete", "hash", "tokenize", "review",
                                         "generalize_for_analyst", "mask_for_analyst", "review_minimization"} for action in actions):
        raise ValueError("Unrecognized scanner recommendation")
    if row["risk_level"] not in {"rendah", "sedang", "tinggi", "kritis"}:
        raise ValueError("Unrecognized risk level")
    # Never copy sample_masked, free-text source reasons, or row values into the profile.
    return {"detected_type": row["detected_type"], "pdp_class": row.get("pdp_class", ""),
            "risk_level": row["risk_level"], "confidence": confidence, "priority_score": priority,
            "triage": row["triage"], "recommendation": row["recommendation"],
            "candidate_aead": "encrypt" in actions, "candidate_bidx": "blind_index" in actions,
            "minimization_candidate": "delete" in actions or "review_minimization" in actions}


def build(inventory: Path, overrides: Path, contract: Path) -> dict:
    expected = contract_columns(contract)
    rows = load_inventory(inventory, set(expected))
    decisions = yaml.safe_load(overrides.read_text(encoding="utf-8"))
    if decisions["protection_version"] != 1 or set(decisions["columns"]) != set(expected):
        raise ValueError("Overrides must cover the v1 contract exactly")
    fields = {}
    for column, required in expected.items():
        decision = decisions["columns"][column]
        if (set(decision) != {"domain","aead","bidx","normalization","analyst_projection","reason"}
                or type(decision.get("aead")) is not bool or type(decision.get("bidx")) is not bool
                or any(decision.get(key) != value for key, value in required.items())):
            raise ValueError("Team override conflicts with the binding contract")
        normalization = NORMALIZATION.get(column)
        projection = column if not required["aead"] else ("age_band" if column == "tanggal_lahir" else None)
        if decision.get("normalization") != normalization or decision.get("analyst_projection") != projection or not decision.get("reason"):
            raise ValueError("Invalid normalization, projection, or rationale")
        finding = assessment(rows[column])
        fields[column] = {**decision, "storage_column": column + "_ct" if required["aead"] else column,
            "wrapped_dek_column": {"PII": "dek_pii_wrapped", "FIN": "dek_fin_wrapped"}.get(required["domain"]),
            "bidx_column": column + "_bidx" if required["bidx"] else None,
            "assessment": finding,
            "override_changes_scanner_action": finding["candidate_aead"] != required["aead"]
                or finding["candidate_bidx"] != required["bidx"] or finding["minimization_candidate"]}
    if decisions["age_band_width"] != 10 or str(decisions["reference_date"]) != "2026-10-01":
        raise ValueError("The shared age-band reference must remain explicit and reproducible")
    resolved = inventory.resolve()
    source_name = resolved.relative_to(ROOT).as_posix() if resolved.is_relative_to(ROOT) else inventory.name
    return {"profile_version": 1, "protection_version": 1, "source_table": "public.anggota", "target_table": "public.anggota_protected",
        "provenance": {"inventory": source_name,
            "inventory_sha256": hashlib.sha256(inventory.read_bytes()).hexdigest(),
            "overrides_sha256": hashlib.sha256(overrides.read_bytes()).hexdigest(),
            "contract_sha256": hashlib.sha256(contract.read_bytes()).hexdigest()},
        "record_id": {"type": "uuid4", "source_mapping": "id -> legacy_row_id"},
        "null_policy": "preserve_null", "ciphertext": {"algorithm": "AES-256-GCM", "format": "01||nonce12||ciphertext||tag16",
            "aad": "dpr|v1|anggota_protected|<column>|<lowercase_uuid>|<protection_version>"},
        "blind_index": {"algorithm": "HMAC-SHA256", "provider": "OpenBao Transit", "key": "search-hmac", "key_version": 1,
            "message": "bidx|v1|<column>|<normalized>", "bytes": 32},
        "derived": {"age_band": {"source": "tanggal_lahir", "reference_date": str(decisions["reference_date"]),
            "width_years": 10, "encoding": "lower-upper", "analyst_projection": True}},
        "columns": fields}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=Path("evidence/scanner/before_v1/inventory.csv"))
    parser.add_argument("--overrides", type=Path, default=Path("policy/overrides.yaml"))
    parser.add_argument("--contract", type=Path, default=Path("docs/contracts/CONTRACT.md"))
    parser.add_argument("--output", type=Path, default=Path("policy/protection_profile.yaml"))
    args = parser.parse_args()
    report = {"schema_version": 1, "passed": False, "checked_at_utc": datetime.now(timezone.utc).isoformat()}
    try:
        profile = build(args.inventory, args.overrides, args.contract)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(yaml.safe_dump(profile, sort_keys=False, allow_unicode=True), encoding="utf-8")
        report.update(passed=True, provenance=profile["provenance"], column_count=len(profile["columns"]),
            aead_columns=sum(field["aead"] for field in profile["columns"].values()),
            blind_index_columns=sum(field["bidx"] for field in profile["columns"].values()),
            scanner_action_overrides=sum(field["override_changes_scanner_action"] for field in profile["columns"].values()))
    except (ValueError, TypeError, KeyError, OSError, yaml.YAMLError):
        report["error"] = "profile_build_failed_details_withheld"
    output = ROOT / "evidence/policy/build-profile.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Protection profile: " + ("PASS" if report["passed"] else "FAIL"))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
