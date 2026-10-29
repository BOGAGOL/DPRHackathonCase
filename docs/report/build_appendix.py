"""Prepare report-local inventory/risk CSVs and byte-exact metadata evidence copies."""

import csv
import hashlib
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
EVIDENCE = (
    "evidence/scanner/evaluation_v1_2.json",
    "evidence/scanner/evaluation_regex_only.json",
    "evidence/scanner/disguised_names.json",
    "evidence/benchmark/bppb_compare.json",
    "evidence/benchmark/bppb_v2_compare.json",
    "evidence/benchmark/api_bppb_compare.json",
    "evidence/benchmark/bppb_session.json",
    "evidence/benchmark/bppb_v2_session.json",
    "evidence/benchmark/bppb_100k/summary.json",
    "evidence/benchmark/bppb_1m/summary.json",
    "evidence/benchmark/bppb_v2_100k/summary.json",
    "evidence/benchmark/bppb_v2_1m/summary.json",
    "evidence/benchmark/active_measurements.json",
    "evidence/access-control/analyst_suppression.json",
    "evidence/backup/service-recovery-integration.json",
    "evidence/acceptance/deployed-browser.json",
    "app/evidence/access-control/vm-pentest-summary.json",
    "app/evidence/access-control/vm-a5-verify.json",
)
RAW_ROOTS = tuple(
    "evidence/benchmark/" + name
    for name in ("bppb_100k", "bppb_1m", "bppb_v2_100k", "bppb_v2_1m")
)


def sha(path, text=False):
    raw = path.read_bytes()
    return hashlib.sha256(raw.replace(b"\r\n", b"\n") if text else raw).hexdigest()


def read_csv(path):
    return list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    path.write_text(buffer.getvalue(), encoding="utf-8")


def inventory_rows(scanner, columns):
    """Keep 29 source attributes; never publish the scanner's actual sample values."""
    by_name = {row["column"]: row for row in scanner}
    rows = []
    for column in columns:
        row = dict(by_name[column["column"]])
        row["sample_masked"] = column["safe_pattern_description"]
        row["pattern_origin"] = (
            "schematic shape from report; not a copied source sample"
        )
        row["truth_pdp_class"] = column["truth_pdp_class"]
        row["review_status"] = "NEEDS_HUMAN_REVIEW"
        rows.append(row)
    return rows


def build(root=ROOT, here=HERE):
    snapshot = json.loads((here / "evidence_snapshot.json").read_text(encoding="utf-8"))
    scanner_source = "evidence/scanner/before_v1_2/inventory.csv"
    profile_source = "evidence/scanner/before_v1/inventory.csv"
    risk_source = "docs/security/risk-matrix.csv"
    columns = snapshot["profile_columns"]
    inventory = inventory_rows(read_csv(root / scanner_source), columns)
    write_csv(here / "tables/inventory-report.csv", inventory)
    factors = {row["column"]: row for row in read_csv(root / profile_source)}
    risk = read_csv(root / risk_source)
    for row in risk:
        row.update(
            {
                key: factors[row["column"]][key]
                for key in (
                    "f_sensitivity",
                    "f_volume",
                    "f_exposure",
                    "f_exploitability",
                    "f_impact",
                    "f_recovery",
                )
            }
        )
        row["factor_source"] = profile_source
        row["score_scope"] = (
            "initial scanner/profile assessment; not residual production risk"
        )
    write_csv(here / "tables/risk-matrix.csv", risk)

    copies = {}
    for name in EVIDENCE:
        # Names are explicitly reviewed; never recurse into credentials or dataset trees.
        source = root / name
        relative = (
            ("service-app/" + name.removeprefix("app/evidence/"))
            if name.startswith("app/evidence/")
            else name.removeprefix("evidence/")
        )
        destination = here / "evidence" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
        copies[destination.relative_to(here).as_posix()] = {
            "source": name,
            "sha256_lf": sha(source, text=True),
            "bytes_at_copy": source.stat().st_size,
        }
    raw = [
        {
            "repository_path": path.relative_to(root).as_posix(),
            "compressed_bytes": path.stat().st_size,
            "sha256": sha(path),
            "included_in_report_folder": False,
        }
        for prefix in RAW_ROOTS
        for path in sorted((root / prefix).rglob("*.gz"))
    ]
    write_csv(here / "tables/raw-benchmark-index.csv", raw)
    report = {
        "schema_version": 1,
        "scope": "Report companion copies/derived tables; no new experiment or human approval",
        "source_files_sha256_lf": {
            name: sha(root / name, text=True)
            for name in (scanner_source, profile_source, risk_source)
        },
        "copies": copies,
        "derived_tables_sha256_lf": {
            name: sha(here / name, text=True)
            for name in (
                "tables/inventory-report.csv",
                "tables/risk-matrix.csv",
                "tables/raw-benchmark-index.csv",
            )
        },
        "inventory": {
            "rows": len(inventory),
            "source_surrogate_id_excluded": True,
            "actual_sample_values_copied": False,
            "scanner_version": "1.2 inventory",
        },
        "risk": {
            "rows": len(risk),
            "factor_source": profile_source,
            "human_approved": False,
        },
        "raw_benchmark": {
            "files_found": len(raw),
            "compressed_bytes": sum(r["compressed_bytes"] for r in raw),
            "copied": False,
            "reason": "Retained in repository; report folder contains path/size/hash index, not another raw-data copy",
        },
    }
    (here / "appendix_manifest.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "inventory_rows": len(inventory),
        "risk_rows": len(risk),
        "evidence_copies": len(copies),
        "raw_files_indexed": len(raw),
    }


if __name__ == "__main__":
    print(json.dumps(build()))
