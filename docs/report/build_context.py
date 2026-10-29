"""Refresh report-only tables/snapshots from reviewed public metadata; never query services."""

import csv
import hashlib
import io
import json
from pathlib import Path
from statistics import median
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import yaml
from infra.submission import sbom


def fingerprint(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def benchmark_rows(compare, variant):
    rows = []
    for scale, scenarios in compare["scales"].items():
        for item in scenarios:
            before, after = item["before"], item["after"]
            rows.append(
                {
                    "variant": variant,
                    "scale": scale,
                    "scenario": item["scenario"],
                    "runs_per_mode": before["runs"],
                    **{
                        f"{mode}_{key}": value[key]
                        for mode, value in (("B", before), ("P", after))
                        for key in (
                            "p50_ms",
                            "p95_ms",
                            "throughput_rps",
                            "error_rate",
                            "db_time_ms_per_request",
                            "non_db_mean_ms",
                        )
                    },
                    "p95_ratio": item["p95_ratio"],
                    "p95_delta_ms": item["p95_delta_ms"],
                    "throughput_ratio": item["throughput_ratio"],
                    **{
                        key: item[key]
                        for key in (
                            "P01_ratio_passed",
                            "P01_absolute_passed",
                            "P02_passed",
                            "P03_passed",
                        )
                    },
                }
            )
    return rows


def resource_rows(runs, scale):
    rows = []
    for mode, scenario in sorted({(r["mode"], r["scenario"]) for r in runs}):
        selected = [r for r in runs if (r["mode"], r["scenario"]) == (mode, scenario)]
        metrics = sorted(selected[0]["resources"])
        row = {
            "scale": scale,
            "mode": mode,
            "scenario": scenario,
            "runs": len(selected),
        }
        for key in metrics:
            values = [r["resources"][key] for r in selected]
            row[key] = (
                sum(values)
                if key in ("samples", "failed_samples")
                else max(values) if key.endswith("peak") else median(values)
            )
        rows.append(row)
    return rows


def markdown_table(rows, columns):
    def display(value):
        if value is None:
            return "—"
        if isinstance(value, bool):
            return "PASS" if value else "FAIL"
        if isinstance(value, float):
            return f"{value:.6f}"
        return str(value).replace("|", "\\|").replace("\n", " ")

    return "\n".join(
        [
            "| " + " | ".join(label for _, label in columns) + " |",
            "|" + "---|" * len(columns),
        ]
        + [
            "| " + " | ".join(display(row.get(key)) for key, _ in columns) + " |"
            for row in rows
        ]
    )


def build(root=ROOT, here=HERE):
    sources = set()

    def read(name):
        sources.add(name)
        return json.loads((root / name).read_text(encoding="utf-8"))

    def write(name, value):
        path = here / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    def csv_file(name, rows):
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        path = here / "tables" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(stream.getvalue(), encoding="utf-8")

    sources.update(("policy/protection_profile.yaml", "scanner/ground_truth_eval.csv"))
    profile = yaml.safe_load(
        (root / "policy/protection_profile.yaml").read_text(encoding="utf-8")
    )
    truth = {
        r["column"]: r
        for r in csv.DictReader(
            (root / "scanner/ground_truth_eval.csv")
            .read_text(encoding="utf-8-sig")
            .splitlines()
        )
    }
    patterns = {
        "no_ktp": "ASCII digits{14} on source; not a validated national NIK",
        "rekening": "digits{16}",
        "npwp": "digits{15}",
        "nip_kppn": "digits{18}",
        "email": "local-part@domain; string",
        "tanggal_lahir": "YYYY-MM-DD",
        "tanggal_pernikahan": "YYYY-MM-DD or NULL",
        "telpon_jakarta": "phone-like text",
        "telpon_daerah": "phone-like text",
        "handphone": "phone-like text",
    }
    columns = [
        {
            "column": name,
            "location": "public.anggota." + name,
            "truth_detected_type": truth[name]["detected_type"],
            "safe_pattern_description": patterns.get(
                name,
                (
                    "small integer"
                    if name.startswith("jumlah_")
                    else "UTF-8 text/category; see source type"
                ),
            ),
            "truth_pdp_class": truth[name]["pdp_class"],
            "truth_risk": truth[name]["risk_level"],
            "scanner_risk": config["assessment"]["risk_level"],
            "domain": config["domain"] or "REF",
            "storage": config["storage_column"],
            "aead": config["aead"],
            "bidx": config["bidx_column"],
            "normalization": config["normalization"],
            "analyst_projection": config["analyst_projection"],
            "reason": config["reason"],
            "review_status": "NEEDS_HUMAN_REVIEW",
        }
        for name, config in profile["columns"].items()
    ]
    comparisons = [
        ("naive_v1", read("evidence/benchmark/bppb_compare.json")),
        ("v2", read("evidence/benchmark/bppb_v2_compare.json")),
    ]
    benchmark = [
        row for variant, data in comparisons for row in benchmark_rows(data, variant)
    ]
    resources = []
    for scale in ("100k", "1m"):
        summary = read(f"evidence/benchmark/bppb_v2_{scale}/summary.json")
        resources.extend(resource_rows(summary["all_runs"], scale))

    after = read("evidence/leakage/after_summary.json")
    leakage, residual, els = [], [], []
    for scale in ("100k", "1m"):
        baseline_name = (
            "evidence/leakage/baseline_100k/baseline_dump.json"
            if scale == "100k"
            else "evidence/leakage/baseline_dump.json"
        )
        base = read(baseline_name)["populations"]["all"]
        entries = [
            {
                "dataset": "baseline_" + scale,
                "scenario": "baseline_dump",
                "ESCE": base["ESCE"],
                "DIE": base["DIE"],
            }
        ]
        entries.extend(
            item
            for item in after["scenarios"]
            if item["dataset"] == "protected_" + scale
        )
        for entry in entries:
            leakage.append(
                {
                    "dataset": entry["dataset"],
                    "scenario": entry["scenario"],
                    "ESCE_numerator": entry["ESCE"]["numerator"],
                    "ESCE_denominator": entry["ESCE"]["denominator"],
                    "ESCE_percent": entry["ESCE"]["ratio"] * 100,
                    "DIE_numerator": entry["DIE"]["numerator"],
                    "DIE_denominator": entry["DIE"]["denominator"],
                    "DIE_percent": entry["DIE"]["ratio"] * 100,
                }
            )
        value = read(f"evidence/leakage/protected_{scale}/residual_after.json")
        for population, group in value["populations"].items():
            rows = group["combinations"]
            residual.append(
                {
                    "dataset": "protected_" + scale,
                    "population": population,
                    "projections_measured": len(rows),
                    "max_attributes_per_projection": max(
                        len(r["columns"]) for r in rows
                    ),
                    "k_min_over_projections": min(r["k_min"] for r in rows),
                    "max_singleton_rows_in_one_projection": max(
                        r["unique_rows"] for r in rows
                    ),
                }
            )
        no_key = read(f"evidence/leakage/protected_{scale}/protected_dump_no_key.json")
        for item in no_key["ELS"]["columns"]:
            els.append(
                {
                    "scale": scale,
                    **{
                        key: item[key]
                        for key in (
                            "column",
                            "storage",
                            "equality_classes",
                            "largest_class",
                            "non_null_cells",
                        )
                    },
                }
            )

    migrations = []
    for scale in ("734", "100k", "1m"):
        name = f"evidence/migration/validation-protected_{scale}.json"
        data = read(name)
        migrations.append(
            {
                "target": "protected_" + scale,
                "source": data["source"],
                "passed": data["passed"],
                "rows_compared": data["rows_compared"],
                "comparison": data["comparison"],
                "checked_at_utc": data["checked_at_utc"],
                "evidence": name,
            }
        )
    scanner = {
        name: {
            key: data[key]
            for key in (
                "in_sample",
                "method",
                "precision",
                "recall",
                "f1",
                "detected_type_accuracy",
                "pdp_class_accuracy",
                "confusion_matrix",
            )
        }
        for name, data in (
            (method, read(f"evidence/scanner/{filename}"))
            for method, filename in (
                ("combined", "evaluation_v1_2.json"),
                ("regex_only", "evaluation_regex_only.json"),
            )
        )
    }
    dependencies = []
    for component in sbom.python_components(root):
        props = {p["name"]: p["value"] for p in component["properties"]}
        dependencies.append(
            {
                "ecosystem": "Python",
                "name": component["name"],
                "declared_version": component.get("version", "UNRESOLVED_RANGE"),
                "constraint": props["dpr:constraint"],
                "declared_in": props["dpr:declared-in"],
            }
        )
    for component in sbom.node_components(root):
        dependencies.append(
            {
                "ecosystem": "npm lock",
                "name": component["name"],
                "declared_version": component["version"],
                "constraint": "lockfile",
                "declared_in": "app/web/package-lock.json",
            }
        )
    sbom_inputs = sbom.inputs(root)
    sources.update(sbom_inputs)
    for filename, components, scope in (
        (
            "python-declared.cdx.json",
            sbom.python_components(root),
            "Declared direct/build/test Python only; unresolved ranges are not installed versions",
        ),
        (
            "frontend-lock.cdx.json",
            sbom.node_components(root),
            "npm lockfile packages; not independently fetched tarballs",
        ),
        (
            "infrastructure.cdx.json",
            sbom.infrastructure_components(root),
            "Compose image references; no OS packages or resolved image digests",
        ),
    ):
        write(
            "appendix/sbom/" + filename,
            sbom.document(filename, components, sbom_inputs, scope),
        )

    snapshot = {
        "schema_version": 1,
        "basis_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
        "scope": "Report context derived from committed project metadata; no services queried or experiments rerun",
        "organizer_pdfs": [
            {
                "id": "R01",
                "name": "signed-2026920-SOAL FINAL HACKATHON DPR RI 2026.pdf",
                "pages": 4,
                "sha256": "5d4f7e337122dffa1659cef7864293f26cd54e06722f2d8c0fd579e04bc01ac9",
            },
            {
                "id": "R02",
                "name": "DPR RI_ Detail Hackaton Syarat Peserta, Proses Penjurian.docx.pdf",
                "pages": 8,
                "sha256": "b5ae5205fb902fc270b29dabb503fc730be2649a8031c2f93ba7c46509850b83",
            },
        ],
        "profile_columns": columns,
        "scanner": scanner,
        "migration": migrations,
        "db_benchmark": benchmark,
        "v2_resources": resources,
        "leakage": leakage,
        "residual": residual,
        "equality_surface": els,
        "api": read("evidence/benchmark/api_bppb_compare.json"),
        "backup_active_baseline": read("evidence/benchmark/active_measurements.json"),
        "dependency_scope": {
            "python_declarations": len(sbom.python_components(root)),
            "npm_lock_entries": len(sbom.node_components(root)),
            "image_references": len(sbom.infrastructure_components(root)),
            "transitive_python_complete": False,
            "deployment_os_inventory_complete": False,
        },
    }
    operations = {}
    operation_fields = {
        "evidence/backup/backup-report.json": (
            "passed",
            "source_database",
            "source_rows",
            "size_bytes",
            "backup_seconds",
            "encryption",
            "dump_role",
        ),
        "evidence/backup/restore-report.json": (
            "passed",
            "mode",
            "source_rows",
            "size_bytes",
            "restore_seconds",
            "manifest_hmac_verified",
            "sha256_verified",
            "all_frames_authenticated_before_restore",
            "plaintext_dump_files",
            "decryption_smoke",
            "service_scope",
        ),
        "evidence/backup/tamper.json": (
            "passed",
            "modified_bytes",
            "original_unchanged",
            "rejected_before_database_creation",
            "rejection",
            "restore_rejected",
        ),
        "evidence/backup/retention.json": (
            "passed",
            "scope",
            "original_source_not_modified",
            "new_backup_restore_member_absent",
            "old_backup_still_contains_member_until_expiry",
            "physical_secure_erasure_claimed",
        ),
        "evidence/keys/rotation.json": (
            "passed",
            "status",
            "target_version",
            "overall_rewrapped_rows",
            "overall_before_versions",
            "validation",
            "resumed",
            "minimum_key_versions_changed",
            "plaintext_or_deks_written",
        ),
        "evidence/overnight/migration_1m/completion.json": (
            "passed",
            "rows_compared",
            "migration_database_role_nologin",
            "migration_token_revoked_and_rejected",
            "database_size_bytes",
            "protected_to_baseline_1m_ratio",
        ),
        "app/evidence/access-control/vm-pentest-summary.json": (
            "status",
            "scope",
            "provenance",
            "database",
            "members",
            "migration_status",
            "pentest_accounts",
            "demo_login_roles",
            "demo_accounts_preserved",
            "setup_member_data_modified",
            "a5_checks",
            "actual_reset_test",
            "reset_smoke_checks",
            "reset_smoke_all_passed",
            "not_verified",
        ),
    }
    for name, fields in operation_fields.items():
        data = read(name)
        operations[name] = {key: data[key] for key in fields if key in data}
    for name in (
        "evidence/access-control/analyst_suppression.json",
        "evidence/backup/service-recovery-integration.json",
        "evidence/acceptance/deployed-browser.json",
    ):
        data = read(name)
        operations[name] = {
            "status": data.get("status"),
            "passed": data.get("passed"),
            "checks": len(data["checks"]),
            "all_checks_passed": all(data["checks"].values()),
            "scope": data.get("scope", "Read narrative for fixture/environment scope"),
        }
    snapshot["operations"] = operations
    for name, rows in (
        ("column-matrix.csv", columns),
        ("db-benchmark.csv", benchmark),
        ("v2-resources.csv", resources),
        ("leakage.csv", leakage),
        ("residual.csv", residual),
        ("equality-surface.csv", els),
        ("migration.csv", migrations),
        ("dependencies.csv", dependencies),
    ):
        csv_file(name, rows)
    write("evidence_snapshot.json", snapshot)

    table_sections = [
        "# 11. Tabel siap olah untuk laporan\n\nAngka penuh ada di CSV/JSON; Markdown membulatkan6desimal. PASS/FAIL menunjukkan hasil target atau boolean sesuai kolom, bukan kelengkapan lomba.\n",
        "## Matriks29kolom\n\nKelas acuan, risiko acuan dan risiko scanner dapat berbeda; domain bukan kelas hukum. Proyeksi analis adalah bahan agregat A5, bukan hak per-record.\n\n"
        + markdown_table(
            columns,
            [
                ("column", "Kolom"),
                ("truth_pdp_class", "Kelas acuan"),
                ("truth_risk", "Risiko acuan"),
                ("scanner_risk", "Risiko scanner"),
                ("domain", "Domain"),
                ("storage", "Storage"),
                ("bidx", "Bidx"),
                ("normalization", "Normalisasi"),
            ],
        ),
        "## Validasi migrasi\n\n"
        + markdown_table(
            migrations,
            [
                ("target", "Target"),
                ("source", "Source"),
                ("rows_compared", "Baris"),
                ("comparison", "Validasi"),
                ("passed", "Hasil"),
            ],
        ),
        "## ESCE dan DIE —25field AEAD non-NULL\n\n"
        + markdown_table(
            leakage,
            [
                ("dataset", "Dataset"),
                ("scenario", "Skenario"),
                ("ESCE_numerator", "ESCE n"),
                ("ESCE_denominator", "ESCE d"),
                ("ESCE_percent", "ESCE %"),
                ("DIE_percent", "DIE %"),
            ],
        ),
        "## Residual1–3atribut\n\n"
        + markdown_table(
            residual,
            [
                ("dataset", "Dataset"),
                ("population", "Populasi"),
                ("projections_measured", "Proyeksi"),
                ("k_min_over_projections", "Minimum k"),
                (
                    "max_singleton_rows_in_one_projection",
                    "Maks baris singleton satu proyeksi",
                ),
            ],
        ),
    ]
    for variant in ("naive_v1", "v2"):
        table_sections.append(
            "## DB "
            + variant
            + " —median4run/mode/skenario\n\n"
            + markdown_table(
                [r for r in benchmark if r["variant"] == variant],
                [
                    ("scale", "Skala"),
                    ("scenario", "Skenario"),
                    ("B_p50_ms", "B p50 ms"),
                    ("P_p50_ms", "P p50 ms"),
                    ("B_p95_ms", "B p95 ms"),
                    ("P_p95_ms", "P p95 ms"),
                    ("B_throughput_rps", "B req/s"),
                    ("P_throughput_rps", "P req/s"),
                    ("P01_ratio_passed", "P01"),
                    ("P01_absolute_passed", "P01A"),
                    ("P02_passed", "P02"),
                    ("P03_passed", "P03"),
                ],
            )
        )
    table_sections.append(
        "## Resource v2\n\nCPU one-core%, median dari median per-run; RAM bytes; peak lengkap dan DB/Bao/client ada di tables/v2-resources.csv. Nilai>100% CPU tidak otomatis salah.\n\n"
        + markdown_table(
            resources,
            [
                ("scale", "Skala"),
                ("mode", "Mode"),
                ("scenario", "Skenario"),
                ("db_cpu_percent_one_core_median", "DB CPU%"),
                ("client_cpu_percent_one_core_median", "Client CPU%"),
                ("openbao_cpu_percent_one_core_median", "Bao CPU%"),
                ("db_ram_bytes_median", "DB RAM bytes"),
                ("client_ram_bytes_median", "Client RAM bytes"),
                ("samples", "Sampel"),
            ],
        )
    )
    table_sections.append(
        "## Dependensi/SBOM\n\n```json\n"
        + json.dumps(snapshot["dependency_scope"], indent=2)
        + "\n```"
        + "\n\nDaftar lengkap deklarasi Python/entri npm ada di tables/dependencies.csv; tiga CycloneDX1.6 ada di appendix/sbom/. Ini bukan SBOM environment deploy lengkap atau sertifikat CVEbersih.\n"
    )
    (here / "11_TABEL_HASIL.md").write_text(
        "\n\n".join(table_sections).rstrip() + "\n", encoding="utf-8"
    )

    code_sources = [
        "docs/contracts/CONTRACT.md",
        "docs/ground_truth_methodology.md",
        "docs/targets.md",
        "infra/NOTES.md",
        "infra/openbao/init.py",
        "infra/postgres/enable_tls.py",
        "infra/vm/README.md",
        "migration/README.md",
        "migration/runner.py",
        "scripts/backup/README.md",
        "scripts/backup/runner.py",
        "infra/rotation/runner.py",
        "sql/protected/01_schema.sql",
        "sql/protected/03_analyst_suppression.sql",
        "sql/roles/01_roles.sql",
        "toolkit/dprcrypto/codec.py",
        "toolkit/dprcrypto/openbao.py",
        "toolkit/dprcrypto/keys.py",
        "toolkit/dprcrypto/bidx.py",
        "toolkit/dprcrypto/https_pool.py",
        "toolkit/dprcrypto/masking.py",
        "app/backend/service_app/policy.py",
        "app/backend/service_app/config.py",
        "app/backend/service_app/models.py",
        "app/backend/service_app/schemas.py",
        "app/backend/service_app/main.py",
        "app/backend/service_app/repository.py",
        "app/backend/service_app/analytics.py",
        "app/backend/service_app/crypto.py",
        "app/scripts/run_runtime.sh",
        "app/deploy/dpr-api.service",
        "app/deploy/dpr-web.service",
        "scripts/deploy/install_app_services.sh",
        "evidence/keys/rotation.json",
        "evidence/backup/backup-report.json",
        "evidence/backup/restore-report.json",
        "evidence/backup/tamper.json",
        "evidence/backup/retention.json",
        "evidence/backup/service-recovery-integration.json",
        "evidence/acceptance/deployed-browser.json",
        "evidence/acceptance/post-a5-summary.json",
        "evidence/access-control/analyst_suppression.json",
        "evidence/overnight/migration_1m/completion.json",
        "evidence/migration/laptop-timings.json",
        "evidence/crypto/vectors.json",
        "evidence/crypto/integration.json",
        "evidence/policy/build-profile.json",
        "evidence/submission/main-sync-20261029.json",
        "app/evidence/access-control/vm-pentest-summary.json",
        "app/evidence/access-control/vm-a5-verify.json",
        "app/evidence/access-control/vm-golden-reset.json",
        "evidence/benchmark/bppb_v2_session.json",
        "evidence/benchmark/bppb_session.json",
        "evidence/benchmark/baseline/env.json",
        "evidence/benchmark/bppb_v2_preflight.json",
        "evidence/scanner/disguised_names.json",
        "toolkit/REVIEW_KEY_SERVICE_LATENCY.md",
    ]
    sources.update(code_sources)
    write(
        "source_manifest.json",
        {
            "schema_version": 1,
            "basis_commit": snapshot["basis_commit"],
            "hash_mode": "SHA256 with CRLF normalized to LF",
            "source_files": {
                name: fingerprint(root / name) for name in sorted(sources)
            },
            "scope": "Selected public metadata and implementation sources only; no dataset, private credentials or known values read by this builder",
        },
    )
    chapters = sorted(here.glob("[0-9][0-9]_*.md"))
    header = "# Konteks lengkap penulisan laporan — BOGAGOL\n\nSnapshot 29 Oktober 2026 WIB, kode 4877fc7/main 96c9edb. Ini konteks lengkap, bukan PDF final.\n\n"
    (here / "CONTEXT.md").write_text(
        header
        + "\n\n---\n\n".join(p.read_text(encoding="utf-8").rstrip() for p in chapters)
        + "\n",
        encoding="utf-8",
    )
    return {
        "source_files": len(sources),
        "chapters": len(chapters),
        "benchmark_rows": len(benchmark),
        "leakage_rows": len(leakage),
        "columns": len(columns),
        "context_words": len((here / "CONTEXT.md").read_text(encoding="utf-8").split()),
    }


if __name__ == "__main__":
    print(json.dumps(build()))
