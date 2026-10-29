"""Read-only checks for presentation timing, evidence scope, chart math and local links."""

import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent


def digest(path, binary=False):
    raw = path.read_bytes()
    return hashlib.sha256(raw if binary else raw.replace(b"\r\n", b"\n")).hexdigest()


def validate(here, root=None):
    errors = []
    plan = json.loads((here / "deck_plan.json").read_text(encoding="utf-8"))
    evidence = json.loads((here / "evidence_cards.json").read_text(encoding="utf-8"))
    manifest = json.loads((here / "source_manifest.json").read_text(encoding="utf-8"))
    cards = evidence["cards"]
    slides = plan["slides"]
    topics = {"risiko", "prioritas", "bukti", "kinerja", "penerapan"}
    if (
        len(slides) != 8
        or len({s["id"] for s in slides}) != 8
        or set().union(*(set(s["topics"]) for s in slides)) != topics
    ):
        errors.append({"kind": "slide_or_required_topic_coverage"})
    if (
        sum(s["core_seconds"] for s in slides) != 300
        or sum(s["extended_seconds"] for s in slides) != 840
        or sum(s["demo_seconds"] for s in slides) != 240
        or plan["extended_seconds"] + plan["extended_buffer_seconds"] != 900
        or plan["core_seconds"] != 300
        or plan["extended_seconds"] != 840
        or plan["demo_seconds_included"] != 240
        or any(s["demo_seconds"] > s["extended_seconds"] for s in slides)
    ):
        errors.append({"kind": "timing_budget_mismatch"})
    script = (here / "03_NASKAH_PEMBICARA.md").read_text(encoding="utf-8")
    sections = {
        m[1]: (int(m[2]), len(m[3].split()))
        for m in re.finditer(
            r"^## (S\d\d) — (\d+) detik\n\n(.*?)(?=\n## |\Z)", script, re.M | re.S
        )
    }
    for slide in slides:
        if sections.get(slide["id"]) != (
            slide["core_seconds"],
            slide["core_script_words"],
        ):
            errors.append({"kind": "speech_plan_mismatch", "slide": slide["id"]})
        if any(claim not in cards for claim in slide["claims"]):
            errors.append({"kind": "unknown_claim", "slide": slide["id"]})
        if slide["core_script_words"] > slide["core_seconds"] * 3:
            errors.append(
                {
                    "kind": "speech_exceeds_180_word_per_minute_budget",
                    "slide": slide["id"],
                }
            )
    if len(cards) != 14 or any(
        not c["sources"] or not c["limit"] for c in cards.values()
    ):
        errors.append({"kind": "claim_source_or_limitation_missing"})
    for name, item in manifest["sources"].items():
        if root is not None:
            path = root / name
            if not path.is_file() or digest(path, item["binary"]) != item["sha256"]:
                errors.append({"kind": "source_changed", "path": name})
        if item["local_copy"]:
            path = here / item["local_copy"]
            if not path.is_file() or digest(path, item["binary"]) != item["sha256"]:
                errors.append(
                    {"kind": "local_copy_changed", "path": item["local_copy"]}
                )
    combined = (here / "CONTEXT.md").read_text(encoding="utf-8")
    chapters = sorted(here.glob("[0-9][0-9]_*.md"))
    for path in chapters:
        if path.read_text(encoding="utf-8").rstrip() not in combined:
            errors.append({"kind": "chapter_not_consolidated", "path": path.name})
    for path in here.rglob("*.md"):
        text = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.S)
        for target in re.findall(r"!?\[[^\]]*\]\(([^\n]+?)\)", text):
            target = unquote(target.strip().strip("<>").split("#", 1)[0])
            if not target or re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", target):
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.is_relative_to(here.resolve()) or not resolved.exists():
                errors.append(
                    {
                        "kind": "missing_or_nonlocal_link",
                        "document": path.name,
                        "target": target,
                    }
                )

    def rows(name):
        return list(
            csv.DictReader(
                io.StringIO((here / "tables" / name).read_text(encoding="utf-8"))
            )
        )

    for row, expected in zip(rows("chart-no-key.csv"), cards["K05"]["data"]):
        if (
            row != {k: str(v) for k, v in expected.items()}
            or int(row["denominator"]) <= 0
        ):
            errors.append({"kind": "no_key_chart_mismatch"})
    if len(rows("chart-no-key.csv")) != 4:
        errors.append({"kind": "no_key_chart_row_count"})
    db_chart = rows("chart-db-nik.csv")
    if len(db_chart) != 4 or {(r["scale"], r["mode"]) for r in db_chart} != {
        ("100k", "B"),
        ("100k", "P"),
        ("1m", "B"),
        ("1m", "P"),
    }:
        errors.append({"kind": "db_chart_scale_or_mode_omitted"})
    for row in db_chart:
        expected = next(r for r in cards["K10"]["data"] if r["scale"] == row["scale"])
        mode = row["mode"]
        if (
            row["level"] != "DB"
            or row["cache"] != "OFF"
            or any(
                not math.isclose(float(row[key]), expected[mode + "_" + key])
                for key in ("p50_ms", "p95_ms", "throughput_rps", "error_rate")
            )
        ):
            errors.append(
                {"kind": "db_chart_mismatch", "scale": row["scale"], "mode": mode}
            )
    for row in cards["K10"]["data"]:
        if (
            row["P01_ratio_passed"]
            or row["P01_absolute_passed"]
            or row["P02_passed"]
            or not row["P03_passed"]
            or not math.isclose(row["P_p95_ms"] / row["B_p95_ms"], row["p95_ratio"])
        ):
            errors.append(
                {"kind": "performance_scope_or_target_mismatch", "scale": row["scale"]}
            )
    for row in rows("chart-optimization.csv"):
        old, new = float(row["naive_p95_protected_ms"]), float(
            row["v2_p95_protected_ms"]
        )
        if old <= 0 or not math.isclose(
            float(row["reduction_percent"]), 100 * (old - new) / old
        ):
            errors.append({"kind": "optimization_math_mismatch"})
    if rows("chart-optimization.csv") != [
        {k: str(v) for k, v in row.items()} for row in cards["K11"]["data"]
    ]:
        errors.append({"kind": "optimization_evidence_mismatch"})
    for row in rows("chart-storage.csv"):
        if not math.isclose(float(row["GiB"]), int(row["bytes"]) / 1024**3):
            errors.append({"kind": "storage_unit_mismatch"})
    if rows("chart-storage.csv") != [
        {k: str(v) for k, v in row.items()} for row in cards["K13"]["data"]
    ]:
        errors.append({"kind": "storage_evidence_mismatch"})
    if cards["K12"]["data"]["status"] != "PLANNED" or cards["K12"]["data"]["scenarios"]:
        errors.append({"kind": "api_status_changed_requires_narrative_review"})
    return {
        "schema_version": 1,
        "passed": not errors,
        "source_hashes_checked": root is not None,
        "sources": len(manifest["sources"]),
        "required_topics": sorted(topics),
        "main_slides": len(slides),
        "core_seconds": sum(s["core_seconds"] for s in slides),
        "extended_seconds_including_demo": sum(s["extended_seconds"] for s in slides),
        "demo_seconds_already_included": sum(s["demo_seconds"] for s in slides),
        "claims": len(cards),
        "chapters": len(chapters),
        "errors": errors,
        "scope": "Context/data/timing consistency only; no slide rendering, human rehearsal, live demo or new experiment",
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
