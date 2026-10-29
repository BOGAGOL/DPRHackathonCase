"""Read-only validation of the report context; no service/credential/dataset access."""

import csv
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent


def normalized_hash(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def validate(here, root=None):
    errors = []
    snapshot = json.loads((here / "evidence_snapshot.json").read_text(encoding="utf-8"))
    manifest = json.loads((here / "source_manifest.json").read_text(encoding="utf-8"))
    if root is not None:
        for name, digest in manifest["source_files"].items():
            path = root / name
            if not path.is_file() or normalized_hash(path) != digest:
                errors.append({"kind": "source_changed", "path": name})
    chapters = sorted(here.glob("[0-9][0-9]_*.md"))
    context = (here / "CONTEXT.md").read_text(encoding="utf-8")
    for chapter in chapters:
        if chapter.read_text(encoding="utf-8").rstrip() not in context:
            errors.append({"kind": "chapter_not_consolidated", "path": chapter.name})
    for path in here.rglob("*.md"):
        content = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.S)
        for target in re.findall(r"!?\[[^\]]*\]\(([^\n]+?)\)", content):
            target = unquote(target.strip().strip("<>").split("#", 1)[0])
            if not target or re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", target):
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.is_relative_to(here.resolve()) or not resolved.exists():
                errors.append(
                    {
                        "kind": "nonlocal_or_missing_link",
                        "document": path.relative_to(here).as_posix(),
                        "target": target,
                    }
                )
    for name, key in (
        ("column-matrix.csv", "profile_columns"),
        ("db-benchmark.csv", "db_benchmark"),
        ("v2-resources.csv", "v2_resources"),
        ("leakage.csv", "leakage"),
        ("residual.csv", "residual"),
        ("equality-surface.csv", "equality_surface"),
        ("migration.csv", "migration"),
    ):
        rows = list(
            csv.DictReader(
                (here / "tables" / name).read_text(encoding="utf-8").splitlines()
            )
        )
        expected = snapshot[key]
        if len(rows) != len(expected) or any(
            row != {k: "" if v is None else str(v) for k, v in item.items()}
            for row, item in zip(rows, expected)
        ):
            errors.append({"kind": "table_snapshot_mismatch", "path": name})
    if (
        len(snapshot["profile_columns"]) != 29
        or sum(c["aead"] for c in snapshot["profile_columns"]) != 25
    ):
        errors.append({"kind": "profile_scope_mismatch"})
    for row in snapshot["db_benchmark"]:
        ratio = row["P_p95_ms"] / row["B_p95_ms"]
        throughput = row["P_throughput_rps"] / row["B_throughput_rps"]
        delta = row["P_p95_ms"] - row["B_p95_ms"]
        allowance = (
            5
            if row["scenario"]
            in {"read_by_nik", "read_by_email", "read_profile", "list_page"}
            else 10
        )
        if not (
            math.isclose(ratio, row["p95_ratio"])
            and math.isclose(throughput, row["throughput_ratio"])
            and math.isclose(delta, row["p95_delta_ms"])
            and row["P01_ratio_passed"] == (ratio <= 1.5)
            and row["P01_absolute_passed"] == (delta <= allowance)
            and row["P02_passed"] == (throughput >= 0.7)
            and row["P03_passed"] == (row["P_error_rate"] <= row["B_error_rate"])
        ):
            errors.append(
                {
                    "kind": "benchmark_math_or_target_mismatch",
                    "variant": row["variant"],
                    "scale": row["scale"],
                    "scenario": row["scenario"],
                }
            )
    for row in snapshot["leakage"]:
        if row["ESCE_denominator"] <= 0 or not math.isclose(
            row["ESCE_percent"], 100 * row["ESCE_numerator"] / row["ESCE_denominator"]
        ):
            errors.append(
                {
                    "kind": "invalid_leakage_denominator_or_ratio",
                    "dataset": row["dataset"],
                    "scenario": row["scenario"],
                }
            )
    schema_validation = json.loads(
        (here / "appendix/sbom/schema-validation.json").read_text(encoding="utf-8")
    )
    for name, result in schema_validation["files"].items():
        path = here / "appendix/sbom" / name
        if not result["passed"] or normalized_hash(path) != result["sha256_lf"]:
            errors.append({"kind": "sbom_schema_proof_stale", "path": name})
    appendix = json.loads((here / "appendix_manifest.json").read_text(encoding="utf-8"))
    for name, item in appendix["copies"].items():
        path = here / name
        if not path.is_file() or normalized_hash(path) != item["sha256_lf"]:
            errors.append({"kind": "appendix_evidence_changed", "path": name})
        if root is not None:
            source = root / item["source"]
            if not source.is_file() or normalized_hash(source) != item["sha256_lf"]:
                errors.append(
                    {"kind": "appendix_source_changed", "path": item["source"]}
                )
    for name, digest in appendix["derived_tables_sha256_lf"].items():
        if normalized_hash(here / name) != digest:
            errors.append({"kind": "appendix_table_changed", "path": name})
    if root is not None:
        for name, digest in appendix["source_files_sha256_lf"].items():
            if normalized_hash(root / name) != digest:
                errors.append({"kind": "appendix_source_changed", "path": name})
    return {
        "schema_version": 1,
        "passed": not errors,
        "basis_commit": snapshot["basis_commit"],
        "source_hashes_checked": root is not None,
        "source_files": len(manifest["source_files"]),
        "chapters_consolidated": len(chapters),
        "columns": len(snapshot["profile_columns"]),
        "benchmark_rows": len(snapshot["db_benchmark"]),
        "leakage_rows": len(snapshot["leakage"]),
        "sbom_schema_proofs_checked": len(schema_validation["files"]),
        "appendix_evidence_copies_checked": len(appendix["copies"]),
        "raw_benchmark_files_indexed": appendix["raw_benchmark"]["files_found"],
        "errors": errors,
        "scope": "Source hashes, local links, consolidated chapters, CSV/JSON equality and arithmetic/targets; not a fresh runtime audit or full PII/secret-history scan",
    }


def main():
    root = HERE.parents[1] if (HERE.parents[1] / "toolkit").is_dir() else None
    report = validate(HERE, root)
    (HERE / "context_validation.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
