"""Baseline leak simulation with a set fast path and batched exact-cell fallback."""
import argparse
from collections import Counter
import json
from pathlib import Path
import random
import subprocess
import time
import uuid

from benchmark.common import ROOT, file_hash, require_disk_space, utc_now, write_csv, write_json
from datagen.model import COLUMNS
from .artifacts import copy_rows, expand_dump, private_path
from .known_values import KnownValues, export_database, normalized, row_mac
from .profile import DIRECT, SCENARIOS, SENSITIVE, PendingProtection, protection_plan
from .residual import BeforeAggregation


def compare_rows(known, rows, observer=None):
    fingerprints = known.fingerprints()
    seen = set()
    matched = Counter()
    populations = {scope: {"rows": 0, "direct_exposed_rows": 0, "exposed_cells": Counter()}
                   for scope in ("all", "source_734", "synthetic")}
    pending = []

    def account(row, exposed):
        scope = "source_734" if int(row["id"]) <= 734 else "synthetic"
        for group in ("all", scope):
            populations[group]["rows"] += 1
            populations[group]["exposed_cells"].update(exposed)
            populations[group]["direct_exposed_rows"] += bool(set(exposed) & set(DIRECT))

    def flush():
        expected = known.lookup([int(row["id"]) for row in pending])
        for row in pending:
            values = expected.get(int(row["id"]))
            if values is None:
                matched["unknown_rows"] += 1
                account(row, [])
                continue
            # Exact (column,value) membership; no substring scan, numeric/date
            # canonicalization already happened on export/COPY decoding.
            cells = {(c, v) for c, v in zip(COLUMNS, values) if c in SENSITIVE and v is not None}
            exposed = [c for c in SENSITIVE if row[c] is not None and (c, str(row[c])) in cells]
            account(row, exposed)
        pending.clear()

    for row in rows:
        identifier = int(row["id"])
        if identifier in seen:
            raise ValueError("Duplicate row identity in artifact; refusing double-counting")
        seen.add(identifier)
        if observer:
            observer(row)
        fingerprint = row_mac(known.key, normalized(row))
        if fingerprint in fingerprints:
            fingerprints.remove(fingerprint)
            matched["full_row_hmac_matches"] += 1
            account(row, [c for c in SENSITIVE if row[c] is not None])
        else:
            matched["fallback_rows"] += 1
            pending.append(row)
            if len(pending) == 500:
                flush()
    flush()
    checked = populations["all"]["rows"]
    exact = matched["full_row_hmac_matches"] == known.meta["rows"] == checked
    return {"status": "PASSED" if exact else "PARTIAL", "rows_checked": checked,
            "full_artifact_equals_known_baseline": exact,
            "method": "HMAC-SHA256 full-row hash set (private random key); indexed batch + exact per-row cell set on mismatches",
            "matching_counts": dict(matched), "populations": populations,
            "denominators": known.meta["non_null_cells"], "population_rows": known.meta["population_rows"],
            "missing_or_changed_full_row_fingerprints": len(fingerprints),
            "coverage_note": "Complete-cell lower bounds only if PARTIAL; no zero exposure claim for missing/unsupported input"}


def pending_scenarios(path=None):
    results = []
    for scenario in SCENARIOS[1:]:
        try:
            plan = protection_plan(scenario, path)
            results.append({"scenario": scenario, "status": "BELUM DIUJI", "plan": plan,
                            "reason": "Real protected/backup artifact and Module A crypto hooks not exercised"})
        except PendingProtection as exc:
            results.append({"scenario": scenario, "status": "BELUM DIUJI", "reason": str(exc)})
    return results


def run(artifact, known_path, database="baseline_1m", scenario="baseline_dump"):
    plan = protection_plan(scenario)
    if scenario != "baseline_dump":
        if scenario.startswith("protected_dump_"):
            from .protected_artifact import run as protected_run
            target = database.replace("baseline_", "protected_")
            return protected_run(artifact, known_path, target, scenario)
        raise PendingProtection("Profile accepted; waiting for real artifact format/decryption adapters from Module A")
    if database != "baseline_1m":
        raise ValueError("This authorized verification session is baseline_1m only")
    started = time.perf_counter()
    artifact, known_path = private_path(artifact), private_path(known_path)
    dataset = json.loads((ROOT / "evidence/datasets/baseline_1m.json").read_text(encoding="utf-8"))
    expected_sha = dataset["baseline_checksum_sha256"]
    if file_hash(artifact) != dataset["snapshot"]["sha256"]:
        raise ValueError("Snapshot checksum differs from generation evidence")
    require_disk_space(minimum_bytes=10_000_000_000)
    phases = {}
    if not known_path.exists():
        phase = time.perf_counter()
        export_database(known_path, database, expected_sha)
        phases["export_known_values_s"] = time.perf_counter() - phase
    known = KnownValues(known_path)
    expanded = artifact.parent / "verify" / ("expanded_" + uuid.uuid4().hex + ".sql")
    try:
        if known.meta["baseline_checksum_sha256"] != expected_sha or known.meta["rows"] != 1000000:
            raise ValueError("Known-values ledger differs from validated dataset")
        phase = time.perf_counter()
        expand_dump(artifact, expanded)
        phases["expand_snapshot_s"] = time.perf_counter() - phase
        aggregate = BeforeAggregation()
        reservoir, rng = [], random.Random(42)
        def observe(row):
            aggregate.add(row)
            if len(reservoir) < 1000:
                reservoir.append(tuple(row[c] for c in COLUMNS))
            else:
                index = rng.randrange(aggregate.rows)
                if index < 1000:
                    reservoir[index] = tuple(row[c] for c in COLUMNS)
        phase = time.perf_counter()
        report = compare_rows(known, copy_rows(expanded), observe)
        phases["match_and_aggregate_s"] = time.perf_counter() - phase
        residual = aggregate.results()
        code_files = sorted(p for p in (ROOT / "verify").glob("*.py"))
        provenance = {"code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                      "worktree_code_sha256": {p.relative_to(ROOT).as_posix(): file_hash(p) for p in code_files},
                      "targets_commit": dataset["targets_commit"], "timestamp_utc": utc_now()}
        report.update(scenario=scenario, dataset=database, artifact_sha256=file_hash(artifact),
                      artifact_bytes=artifact.stat().st_size, snapshot_generation_verified=True,
                      known_values_baseline_checksum_sha256=expected_sha,
                      known_values_location="DPR_PRIVATE_DIR/verify (raw cells and matching key not exported)",
                      profile=plan, **provenance)
        residual.update(dataset=database, status=report["status"], **provenance)
        write_json(ROOT / "evidence/leak/baseline_dump.json", report)
        write_json(ROOT / "evidence/leakage/residual_before.json", residual)
        if not report["full_artifact_equals_known_baseline"]:
            raise ValueError("Partial snapshot recovery; no complete baseline budget/ELS claim")
        from .leakage_budget import build_report, summary_rows
        phase = time.perf_counter()
        budget = build_report(known, report, residual)
        phases["equality_budget_s"] = time.perf_counter() - phase
        write_json(ROOT / "evidence/leakage/baseline_dump.json", budget)
        write_csv(ROOT / "evidence/leakage/before_after.csv", summary_rows(budget, residual))
        from .artifact_scanner import scan_reservoir
        phase = time.perf_counter()
        scan_reservoir(reservoir, aggregate.rows, report["artifact_sha256"],
                       residual["populations"]["all"]["combinations"], time.perf_counter() - started,
                       ROOT / "evidence/leak/baseline_dump_scanner")
        phases["artifact_scanner_s"] = time.perf_counter() - phase
        write_json(ROOT / "evidence/leakage/protected_pending.json", {
            "timestamp_utc": utc_now(), "profile_present_in_integrated_tree": (ROOT / "policy/protection_profile.yaml").is_file(),
            "scenarios": pending_scenarios(), "not_claimed": ["protected ESCE=0", "decryption blast radius", "physical data/WAL", "TLS", "S05/S06 operational scan"]})
        report.update(phases_s=phases, total_elapsed_s=time.perf_counter() - started, completed_at_utc=utc_now())
        write_json(ROOT / "evidence/leak/baseline_dump.json", report)
        return report
    finally:
        known.close()
        if expanded.exists():
            expanded.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--known-values", type=Path, required=True)
    parser.add_argument("--scenario", choices=SCENARIOS, required=True)
    parser.add_argument("--db", choices=["baseline_1m", "protected_100k", "protected_1m"], default="baseline_1m")
    args = parser.parse_args()
    try:
        report = run(args.artifact, args.known_values, database=args.db, scenario=args.scenario)
        rows = report["rows_checked"] if "rows_checked" in report else report["populations"]["all"]["rows"]
        elapsed = report["total_elapsed_s"] if "total_elapsed_s" in report else report["elapsed_s"]
        print(json.dumps({"status": report["status"], "rows": rows, "elapsed_s": elapsed}))
    except PendingProtection as exc:
        write_json(ROOT / "evidence/leak" / (args.scenario + ".json"),
                   {"status": "BELUM DIUJI", "scenario": args.scenario, "reason": str(exc), "timestamp_utc": utc_now()})
        raise SystemExit("Protected scenario pending Module A; no exposure score inferred") from None
    except Exception as exc:
        write_json(ROOT / "evidence/leak/failure.json", {"status": "FAILED", "scenario": args.scenario,
                   "exception_type": type(exc).__name__, "timestamp_utc": utc_now(), "private_details_withheld": True})
        raise SystemExit("Verification failed; private details withheld, see evidence/leak/failure.json") from None


if __name__ == "__main__":
    main()
