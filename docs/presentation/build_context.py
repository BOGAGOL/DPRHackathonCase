"""Prepare presentation context from public project metadata; no slides or services."""

import csv
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
TOPICS = {"risiko", "prioritas", "bukti", "kinerja", "penerapan"}
SLIDES = (
    ("S01", "Ketika salinan database bocor", 20, 35, ["risiko"], ["K01"]),
    ("S02", "Risiko utama pada data", 40, 65, ["risiko"], ["K01", "K02", "K06"]),
    ("S03", "Prioritas solusi dan arsitektur", 50, 90, ["prioritas"], ["K03", "K04"]),
    ("S04", "Bukti pelindungan pada salinan data", 50, 100, ["bukti"], ["K05", "K06"]),
    (
        "S05",
        "Akses sah dan pemulihan",
        45,
        300,
        ["bukti"],
        ["K07", "K08", "K09", "K14"],
    ),
    ("S06", "Dampak kinerja DB", 45, 120, ["kinerja"], ["K10", "K11", "K12", "K13"]),
    ("S07", "Tahapan penerapan di instansi", 35, 85, ["penerapan"], ["K13", "K14"]),
    (
        "S08",
        "Hasil, batas dan tindak lanjut",
        15,
        45,
        ["penerapan", "risiko"],
        ["K06", "K12"],
    ),
)


def digest(path, binary=False):
    raw = path.read_bytes()
    return hashlib.sha256(raw if binary else raw.replace(b"\r\n", b"\n")).hexdigest()


def improvement_percent(before, after):
    if before <= 0 or after < 0:
        raise ValueError("Positive baseline and non-negative measured value required")
    return 100 * (before - after) / before


def speaker_sections(text):
    return {
        match[1]: {
            "duration_seconds": int(match[2]),
            "text": match[3].strip(),
            "word_count": len(match[3].split()),
        }
        for match in re.finditer(
            r"^## (S\d\d) — (\d+) detik\n\n(.*?)(?=\n## |\Z)", text, re.M | re.S
        )
    }


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    path.write_text(buffer.getvalue(), encoding="utf-8")


def build(root=ROOT, here=HERE):
    here.mkdir(parents=True, exist_ok=True)
    sources = {}

    def track(name, local=None):
        binary = Path(name).suffix == ".png"
        sources[name] = {
            "sha256": digest(root / name, binary),
            "binary": binary,
            "local_copy": local,
        }

    def read(name):
        track(name)
        return json.loads((root / name).read_text(encoding="utf-8"))

    def write(name, data):
        (here / name).write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    report = read("docs/report/evidence_snapshot.json")
    report_sources = read("docs/report/source_manifest.json")
    read("docs/report/appendix_manifest.json")
    for name in (
        "docs/report/01_KETENTUAN_DAN_LUARAN.md",
        "docs/report/DELIVERABLES_AUDIT.md",
        "policy/protection_profile.yaml",
        "app/backend/service_app/policy.py",
    ):
        track(name)
    lab = read("evidence/backup/service-recovery-integration.json")
    sql = read("evidence/access-control/analyst_suppression.json")
    web = read("evidence/acceptance/deployed-browser.json")
    compare_v2 = read("evidence/benchmark/bppb_v2_compare.json")
    compare_v1 = read("evidence/benchmark/bppb_compare.json")
    api = read("evidence/benchmark/api_bppb_compare.json")
    for name in (
        "db-benchmark.csv",
        "v2-resources.csv",
        "leakage.csv",
        "residual.csv",
        "column-matrix.csv",
    ):
        source, local = "docs/report/tables/" + name, "tables/" + name
        track(source, local)
        path = here / local
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((root / source).read_bytes())
    for name in (
        "architecture.png",
        "architecture.svg",
        "architecture.mmd",
        "data-lifecycle.mmd",
    ):
        source, local = "docs/report/assets/" + name, "assets/" + name
        track(source, local)
        path = here / local
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((root / source).read_bytes())

    nik = [r for r in report["db_benchmark"] if r["scenario"] == "read_by_nik"]
    v2_nik = [r for r in nik if r["variant"] == "v2"]
    no_key = [
        {
            "scale": r["dataset"].rsplit("_", 1)[-1],
            "mode": (
                "baseline" if r["scenario"] == "baseline_dump" else "protected_no_key"
            ),
            "esce_percent": r["ESCE_percent"],
            "numerator": r["ESCE_numerator"],
            "denominator": r["ESCE_denominator"],
            "scope": "25 AEAD non-NULL fields only",
        }
        for r in report["leakage"]
        if r["scenario"] in {"baseline_dump", "protected_dump_no_key"}
    ]
    db_nik = [
        {
            "scale": r["scale"],
            "mode": mode,
            "p50_ms": r[mode + "_p50_ms"],
            "p95_ms": r[mode + "_p95_ms"],
            "throughput_rps": r[mode + "_throughput_rps"],
            "error_rate": r[mode + "_error_rate"],
            "runs_per_mode": r["runs_per_mode"],
            "level": "DB",
            "variant": "v2",
            "cache": "OFF",
        }
        for r in v2_nik
        for mode in ("B", "P")
    ]
    optimizations = []
    for scale in ("100k", "1m"):
        old = next(r for r in nik if r["scale"] == scale and r["variant"] == "naive_v1")
        new = next(r for r in nik if r["scale"] == scale and r["variant"] == "v2")
        optimizations.append(
            {
                "scale": scale,
                "naive_p95_protected_ms": old["P_p95_ms"],
                "v2_p95_protected_ms": new["P_p95_ms"],
                "reduction_percent": improvement_percent(
                    old["P_p95_ms"], new["P_p95_ms"]
                ),
                "comparison_scope": "different declared sessions; not causal isolation",
            }
        )
    sizes = report["operations"]["evidence/overnight/migration_1m/completion.json"][
        "database_size_bytes"
    ]
    storage = [
        {
            "scale": scale,
            "database": prefix + "_" + scale,
            "bytes": sizes[prefix + "_" + scale],
            "GiB": sizes[prefix + "_" + scale] / 1024**3,
            "scope": "recorded migration-completion snapshot",
        }
        for scale in ("100k", "1m")
        for prefix in ("baseline", "protected")
    ]
    for name, rows in (
        ("chart-no-key.csv", no_key),
        ("chart-db-nik.csv", db_nik),
        ("chart-optimization.csv", optimizations),
        ("chart-storage.csv", storage),
    ):
        write_csv(here / "tables" / name, rows)

    columns = report["profile_columns"]
    cards = {
        "K01": {
            "data": {
                "source_rows": 734,
                "source_columns": len(columns),
                "target_scales": [100000, 1000000],
            },
            "sources": [
                "docs/contracts/CONTRACT.md",
                "evidence/migration/validation-protected_1m.json",
            ],
            "limit": "Synthetic competition case; not real DPR operations",
        },
        "K02": {
            "data": report["scanner"],
            "sources": [
                "evidence/scanner/evaluation_v1_2.json",
                "evidence/scanner/evaluation_regex_only.json",
            ],
            "limit": "29 labels; in-sample before final human sign-off",
        },
        "K03": {
            "data": {
                "aead": sum(c["aead"] for c in columns),
                "pii": sum(c["domain"] == "PII" for c in columns),
                "fin": sum(c["domain"] == "FIN" for c in columns),
                "ref": sum(c["domain"] == "REF" for c in columns),
                "bidx": sum(bool(c["bidx"]) for c in columns),
            },
            "sources": ["policy/protection_profile.yaml"],
            "limit": "Source fields, not all operational database columns",
        },
        "K04": {
            "data": {
                "cipher": "AES-256-GCM",
                "field_format_version": 1,
                "nonce_bytes": 12,
                "dek_bytes": 32,
                "app_cache": "OFF",
            },
            "sources": [
                "docs/contracts/CONTRACT.md",
                "app/backend/service_app/crypto.py",
            ],
            "limit": "Local AEAD; memory/OS and shared app-key compromise remain limits",
        },
        "K05": {
            "data": no_key,
            "sources": ["evidence/leakage/after_summary.json"],
            "limit": "ESCE on 25 AEAD non-NULL fields; not all data or inference",
        },
        "K06": {
            "data": {"leakage": report["leakage"], "residual": report["residual"]},
            "sources": [
                "evidence/leakage/after_summary.json",
                "evidence/leakage/protected_1m/residual_after.json",
            ],
            "limit": "FIN/search may expose identifiers; source734 k=1; full synthetic dictionary is upper-bound model",
        },
        "K07": {
            "data": {
                "checks": len(sql["checks"]),
                "threshold": sql["threshold"],
                "passed": sql["passed"],
            },
            "sources": ["evidence/access-control/analyst_suppression.json"],
            "limit": "Isolated SQL fixture; marginal suppression, not DP",
        },
        "K08": {
            "data": {
                "checks": len(lab["checks"]),
                "rows": lab["source_rows"],
                "passed": lab["passed"],
            },
            "sources": ["evidence/backup/service-recovery-integration.json"],
            "limit": lab["scope"],
        },
        "K09": {
            "data": {
                "web_checks": len(web["checks"]),
                "web_status": web["status"],
                "vm_operator": report["operations"][
                    "app/evidence/access-control/vm-pentest-summary.json"
                ],
            },
            "sources": [
                "evidence/acceptance/deployed-browser.json",
                "app/evidence/access-control/vm-pentest-summary.json",
            ],
            "limit": "Separate web/operator evidence; not full pentest or a combined check population",
        },
        "K10": {
            "data": v2_nik,
            "sources": ["evidence/benchmark/bppb_v2_compare.json"],
            "limit": "DB NIK example; all14 scale/scenario combinations fail P01/P01A/P02 and pass P03",
        },
        "K11": {
            "data": optimizations,
            "sources": [
                "evidence/benchmark/bppb_compare.json",
                "evidence/benchmark/bppb_v2_compare.json",
            ],
            "limit": "Between-session improvement; targets still fail",
        },
        "K12": {
            "data": api,
            "sources": ["evidence/benchmark/api_bppb_compare.json"],
            "limit": "PLANNED with no measured scenarios in this snapshot; proposed two repetitions below minimum3",
        },
        "K13": {
            "data": storage,
            "sources": ["evidence/overnight/migration_1m/completion.json"],
            "limit": "Storage snapshot; not production cost/SLA",
        },
        "K14": {
            "data": {
                name: data
                for name, data in report["operations"].items()
                if name.startswith(("evidence/backup/", "evidence/keys/"))
            },
            "sources": [
                "evidence/keys/rotation.json",
                "evidence/backup/restore-report.json",
                "evidence/backup/retention.json",
            ],
            "limit": "Operational/lab evidence; not all-scale key rotation or full key-plane DR",
        },
    }
    for card in cards.values():
        for name in card["sources"]:
            track(name)
    for name in report_sources["source_files"]:
        if name in {"docs/contracts/CONTRACT.md", "app/backend/service_app/crypto.py"}:
            track(name)
    metadata = {
        "basis_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
        "report_snapshot_basis_commit": report["basis_commit"],
        "organizer_pdfs": report["organizer_pdfs"],
        "measurement_context": {
            "level": "DB",
            "concurrency": 8,
            "duration_s": 60,
            "warmup_s": 10,
            "runs_per_mode_scenario": 4,
            "blocks": 2,
            "order": ["B", "P", "P", "B"],
            "cache": "OFF",
        },
        "historical_targets_commit": compare_v2["targets_commit"],
        "historical_production_commit_v2": compare_v2["variant_metadata"][
            "requested_production_commit"
        ],
        "historical_completed_at_utc": compare_v2["completed_at_utc"],
        "scope": "Presentation context and chart data only; no fresh experiments, live login or final deck",
    }
    write(
        "evidence_cards.json",
        {"schema_version": 1, "metadata": metadata, "cards": cards},
    )
    speech = speaker_sections(
        (here / "03_NASKAH_PEMBICARA.md").read_text(encoding="utf-8")
    )
    plan = {
        "schema_version": 1,
        "required_topics": sorted(TOPICS),
        "slides": [
            {
                "id": sid,
                "title": title,
                "core_seconds": core,
                "extended_seconds": extended,
                "demo_seconds": 240 if sid == "S05" else 0,
                "topics": topics,
                "claims": claims,
                "core_script_words": speech[sid]["word_count"],
            }
            for sid, title, core, extended, topics, claims in SLIDES
        ],
        "backup_slide_ids": ["A01", "A02", "A03", "A04", "A05", "A06"],
        "core_seconds": 300,
        "extended_seconds": 840,
        "demo_seconds_included": 240,
        "extended_buffer_seconds": 60,
        "maximum_seconds_including_buffer": 900,
        "qa_maximum_seconds_separate": 600,
        "human_timing_rehearsed": False,
        "live_demo_prepared": False,
        "final_deck_created": False,
        "proposed_plan_not_official_slide_count": True,
    }
    write("deck_plan.json", plan)
    write(
        "source_manifest.json",
        {
            "schema_version": 1,
            "metadata": metadata,
            "sources": dict(sorted(sources.items())),
            "text_hash_mode": "SHA256 after CRLF to LF normalization; PNG hash is byte-exact",
        },
    )
    chapters = sorted(here.glob("[0-9][0-9]_*.md"))
    (here / "CONTEXT.md").write_text(
        "# Konteks lengkap persiapan presentasi — BOGAGOL\n\n"
        "Paket persiapan 29 Oktober 2026 WIB; bukan deck final atau operasi demo baru.\n\n"
        + "\n\n---\n\n".join(
            path.read_text(encoding="utf-8").rstrip() for path in chapters
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "chapters": len(chapters),
        "main_slides": len(plan["slides"]),
        "backup_slides": 6,
        "claims": len(cards),
        "sources": len(sources),
        "core_speech_words": sum(s["word_count"] for s in speech.values()),
    }


if __name__ == "__main__":
    print(json.dumps(build()))
