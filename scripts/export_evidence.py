"""Sanitized evidence index, OpenAPI and dependency inventory; no environment secrets."""
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api"))


def main():
    evidence = ROOT / "evidence"
    browser_raw = json.loads((ROOT / ".local/browser-results.json").read_text(encoding="utf-8"))
    tests = []
    def walk(suite):
        for spec in suite.get("specs", []):
            for test in spec["tests"]:
                result = test["results"][-1]
                tests.append({"scenario": spec["title"], "project": test["projectName"], "status": result["status"], "duration_ms": result["duration"]})
        for child in suite.get("suites", []):
            walk(child)
    for suite in browser_raw.get("suites", []):
        walk(suite)
    (evidence / "browser-tests.json").write_text(json.dumps({"status": "TESTED" if all(t["status"] == "passed" for t in tests) and tests else "FAILED", "tests": tests,
                                                          "privacy": "No cookies, passwords, request/response bodies, traces or raw names exported"}, indent=2), encoding="utf-8")
    from app.config import Settings
    from app.main import create_app
    app = create_app(Settings.from_env())
    (evidence / "openapi.json").write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
    app.state.engine.dispose()
    direct = []
    for line in (ROOT / "apps/api/requirements.txt").read_text().splitlines():
        name, pinned = line.split("==")
        distribution = importlib.metadata.distribution(name.split("[")[0])
        direct.append({"name": name, "version": pinned, "license": distribution.metadata.get("License-Expression") or (distribution.metadata.get("License") or "See upstream metadata").splitlines()[0]})
    lock = json.loads((ROOT / "apps/web/package-lock.json").read_text())
    web = [{"name": name.removeprefix("node_modules/"), "version": item.get("version"), "license": item.get("license", "See upstream metadata"), "integrity": item.get("integrity")} for name, item in lock["packages"].items() if name]
    (evidence / "dependencies.json").write_text(json.dumps({"python_direct": direct, "frontend_lock_inventory": web, "note": "Manifest inventory, not a CVE audit. Python transitive resolved versions listed separately below.",
                                                          "python_transitive": [{"name": d.metadata["Name"], "version": d.version} for d in importlib.metadata.distributions() if d.metadata["Name"] in {"starlette", "anyio", "cffi", "argon2-cffi-bindings", "greenlet", "Mako", "psycopg-binary", "typing_extensions", "annotated-types", "pydantic_core", "typing-inspection", "h11", "httpcore", "idna", "certifi", "click", "colorama", "packaging", "pluggy", "iniconfig", "Pygments", "MarkupSafe", "sniffio", "tomli", "tzdata", "pycparser"}]}, indent=2), encoding="utf-8")
    sections = ["# Pengukuran kinerja lokal\n", "Workload: baca/tulis kontak 80/20, concurrency 1, seed 2026, 300 operasi per konfigurasi per pengulangan, tiga pengulangan dengan urutan bergantian dan 20 warmup reads. Output bisnis setara; ciphertext dikembalikan ke snapshot awal setelah mutasi. Angka berikut adalah median, raw per-operasi tersedia di JSON.\n",
                "Target development ditetapkan di runner sebelum pengujian: p95 < 100 ms dan zero unexpected errors. Workload kecil ini tidak membuktikan kapasitas produksi. CPU/RAM PostgreSQL mencakup process tree cluster native, termasuk background/idle backend; sum working sets dapat menghitung shared pages berulang. Memory runner mencakup snapshot data yang dimuat kedua konfigurasi.\n"]
    for file in ["benchmark.json", "benchmark-scaled.json"]:
        report = json.loads((evidence / file).read_text())
        sections.append(f"## {report['dataset_records']:,} record — {report['timestamp_utc']}\n")
        sections.append("| Metrik median | Baseline | Protected |\n|---|---:|---:|")
        labels = {"p50_ms": "p50 (ms)", "p95_ms": "p95 (ms)", "throughput_success_ops_s": "Throughput sukses (ops/s)", "error_rate": "Unexpected error rate", "runner_cpu_percent_one_core": "CPU runner (% satu core)", "runner_peak_rss_bytes": "Peak working set runner (MiB)", "db_cpu_percent_one_core": "CPU cluster (% satu core)", "db_peak_rss_sum_bytes": "Peak sum working set cluster (MiB)", "database_bytes": "Database keseluruhan (MiB)", "backup_seconds": "Encrypted backup (s)", "restore_seconds": "Restore baru (s)", "encrypted_bytes": "Backup terenkripsi (MiB)"}
        for key, label in labels.items():
            values = [report["median"][mode][key] for mode in ["baseline", "protected"]]
            if key.endswith("_bytes"):
                values = [v / 1024**2 for v in values]
            sections.append(f"| {label} | {values[0]:.4f} | {values[1]:.4f} |")
        overhead = (report["median"]["protected"]["p50_ms"] / report["median"]["baseline"]["p50_ms"]-1)*100
        sections.append(f"\np50 overhead teramati {overhead:.1f}%. Lihat [raw results](../evidence/{file}) untuk durasi enkripsi/dekripsi, distribusi dan variasi antar-run. Backup/restore: pg_dump custom, AES-GCM independen, restore database baru dan validasi count; tiga pengulangan per konfigurasi.\n")
    sections.extend(["## Batas interpretasi\n", "Benchmark ini melewati HTTP, session, CSRF, audit bisnis, TLS dan live OpenBao: **NOT TESTED** untuk metrik performanya. Browser/API functional tests terpisah tidak mengubah batas ini. Storage adalah ukuran seluruh database termasuk schema, audit, users/index dan bloat; bukan ukuran ciphertext saja. Restore tidak memasukkan transfer offsite/KMS recovery. File backup benchmark berada di memori terenkripsi dan tidak dipersist; restore latency termasuk decrypt + create DB + pg_restore. Satu backup protected nyata disimpan lokal oleh backup drill terpisah.\n", "Data scale dibuat dari nol untuk beban uji, tidak menambah anggota aplikasi atau memodifikasi sumber. Perbandingan 734 record mempunyai database yang sudah dipakai tes; 10.000 record memakai DB baru. Durasi sub-milidetik dan tiga pengulangan sensitif terhadap scheduler/cache Windows. p95 yang terkadang lebih rendah pada protected bukan bukti enkripsi mempercepat sistem.\n"])
    (ROOT / "docs/PERFORMANCE.md").write_text("\n".join(sections), encoding="utf-8")
    print(f"Exported sanitized evidence for {len(tests)} browser scenarios and dependency manifests.")


if __name__ == "__main__":
    main()
