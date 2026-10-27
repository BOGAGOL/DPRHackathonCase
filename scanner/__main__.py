"""Usage: python -m scanner {db,dump,files,evaluate} ..."""
import argparse
import os
from pathlib import Path
import random
import sys
import time

import yaml

from . import __version__
from .detection import embedded_findings
from .evaluation import evaluate
from .masking import mask
from .model import Table
from .priority import load_type_policy
from .relations import quasi_combinations
from .reporting import analyze, emit, write_json
from .sources import (DumpSource, InputError, database, database_k, foreign_keys,
                      read_database, safe_db_source)

CONFIG = Path(__file__).parent / "config"


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("harus lebih dari nol")
    return number


def parser():
    root = argparse.ArgumentParser(description="Scanner kandidat data pribadi lokal, read-only, dengan contoh termasking.")
    root.add_argument("--version", action="version", version=__version__)
    sub = root.add_subparsers(dest="command", required=True)
    for name in ("db", "dump", "files"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--out", type=Path, required=True)
        cmd.add_argument("--label", default="before")
        cmd.add_argument("--sample", type=positive, default=1000)
        cmd.add_argument("--weights", type=Path, default=CONFIG / "weights.yaml")
        cmd.add_argument("--environment", type=Path)
        cmd.add_argument("--impact", type=Path, default=CONFIG / "impact.yaml")
        cmd.add_argument("--baseline", choices=["regex_only"])
        if name == "db":
            cmd.add_argument("--schema", default="public")
        elif name == "dump":
            cmd.add_argument("--file", type=Path, required=True)
        else:
            cmd.add_argument("paths", nargs="*", type=Path)
            cmd.add_argument("--file", nargs="+", type=Path, dest="input_files", default=[])
    cmd = sub.add_parser("evaluate")
    cmd.add_argument("--pred", type=Path, required=True)
    cmd.add_argument("--truth", type=Path, required=True)
    cmd.add_argument("--out", type=Path, required=True)
    cmd.add_argument("--label-map", type=Path, default=CONFIG / "label_map.yaml")
    cmd.add_argument("--baseline", choices=["regex_only"])
    return root


def configuration(args):
    with args.weights.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    label = args.label
    if not label or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in label):
        raise InputError("Label hanya boleh huruf, angka, garis bawah, dan tanda minus.")
    path = args.environment or CONFIG / ("environment_" + label + ".yaml")
    if not path.is_file():
        raise InputError("Konfigurasi environment label belum ada; tentukan --environment.")
    with path.open(encoding="utf-8") as handle:
        environment = yaml.safe_load(handle)
    if not isinstance(environment, dict) or set(environment) not in (
        {"volume", "exposure", "recovery"}, {"volume", "exposure", "impact", "recovery"}
    ) or any(
        type(v) is not int or not 1 <= v <= 5 for v in environment.values()
    ):
        raise InputError("Environment wajib memuat volume, exposure, recovery integer 1-5.")
    if "impact" in environment:
        config["legacy_environment_impact_ignored"] = True
        environment = {k: environment[k] for k in ("volume", "exposure", "recovery")}
    try:
        config["type_policy"] = load_type_policy(args.impact)
    except (ValueError, OSError):
        raise InputError("impact.yaml wajib memuat sensitivity dan impact integer 1-5 per jenis.") from None
    if not (0 <= config["content_weight"] <= 1 and 0 <= config["name_weight"] < config["content_weight"]
            and abs(config["content_weight"] + config["name_weight"] - 1) < 1e-9):
        raise InputError("Bobot isi harus lebih besar daripada nama dan totalnya satu.")
    for key in ("auto_content_threshold", "auto_confidence_threshold", "review_threshold"):
        if not 0 <= config[key] <= 100:
            raise InputError("Ambang skor harus antara 0 dan 100.")
    for key in ("minimum_relation_rows", "max_quasi_candidates", "max_combinations", "max_join_pairs"):
        if type(config[key]) is not int or config[key] < 1:
            raise InputError("Batas analisis wajib integer positif.")
    if not 0 < config["relation_threshold"] <= 1:
        raise InputError("Ambang relasi harus lebih dari nol hingga satu.")
    return config, environment


def file_scan(paths, sample, output_directory):
    files = set()
    for path in paths:
        if path.is_dir():
            files.update(p.resolve() for p in path.rglob("*") if p.is_file()
                         and not p.resolve().is_relative_to(output_directory.resolve()))
        elif path.is_file():
            files.add(path.resolve())
        else:
            raise InputError("Salah satu path input tidak ditemukan.")
    if not files:
        raise InputError("Pilih minimal satu file teks untuk dipindai.")
    findings, tables = [], []
    rng = random.Random(2026)
    total_findings = 0
    for path in sorted(files):
        rows, selected, matches, total_lines = [], [], 0, 0
        with path.open(encoding="utf-8-sig", errors="replace") as handle:
            for number, line in enumerate(handle, 1):
                total_lines = number
                value = line.rstrip("\r\n")
                if len(rows) < sample:
                    rows.append((value,))
                else:
                    index = rng.randrange(number)
                    if index < sample:
                        rows[index] = (value,)
                for kind, raw in embedded_findings(value):
                    matches += 1
                    item = {"file": str(path), "line": number, "detected_type": kind, "sample_masked": mask(raw, kind)}
                    if len(selected) < sample:
                        selected.append(item)
                    else:
                        index = rng.randrange(matches)
                        if index < sample:
                            selected[index] = item
        total_findings += matches
        findings.extend(sorted(selected, key=lambda r: r["line"]))
        tables.append(Table(str(path), ["text"], ["text"], rows, total_lines))
    return tables, findings, total_findings


def run(args):
    started = time.perf_counter()
    if args.command == "evaluate":
        result = evaluate(args.pred, args.truth, args.label_map, args.baseline)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.out, result)
        return
    config, environment = configuration(args)
    baseline = args.baseline == "regex_only"
    anonymity, findings = [], None
    if args.command == "db":
        url = os.environ.get("SCANNER_DATABASE_URL")
        with database(url) as conn:
            tables = read_database(conn, args.schema, args.sample)
            if not tables:
                raise InputError("Tidak ada tabel target yang terlihat oleh role scanner.")
            inventory, feature_map, relations = analyze(tables, config, environment, baseline)
            relations["foreign_keys"] = foreign_keys(conn, args.schema)
            for table in tables:
                combos = quasi_combinations(table, feature_map, config) if not baseline else []
                anonymity.extend(database_k(conn, table, combos, args.schema))
            source = safe_db_source(url)
    elif args.command == "dump":
        store = DumpSource(args.sample)
        try:
            tables = store.parse(args.file)
            inventory, feature_map, relations = analyze(tables, config, environment, baseline)
            relations["foreign_keys"] = []
            for table in tables:
                anonymity.extend(store.k_anonymity(table, quasi_combinations(table, feature_map, config) if not baseline else []))
            source = {"mode": "dump", "path": str(args.file.resolve())}
        finally:
            store.close()
    else:
        tables, findings, total_findings = file_scan(args.paths + args.input_files, args.sample, args.out)
        inventory, feature_map, relations = analyze(tables, config, environment, baseline)
        relations["foreign_keys"] = []
        source = {"mode": "files", "paths": [t.name for t in tables], "total_matches": total_findings,
                  "exported_matches": len(findings), "findings_limit_per_file": args.sample,
                  "k_anonymity": "not_applicable_unstructured_text"}
    source["table_counts"] = {t.name: {"total_rows": t.total, "sample_rows": len(t.rows)} for t in tables}
    source["environment_factors"] = environment
    source["type_priority_policy"] = config["type_policy"]
    source["legacy_environment_impact_ignored"] = config.get("legacy_environment_impact_ignored", False)
    source["quasi_limits"] = {k: config[k] for k in ("max_quasi_candidates", "max_combinations")}
    emit(args.out, inventory, feature_map, relations, anonymity, label=args.label,
         source=source, sample=args.sample, duration=time.perf_counter() - started,
         baseline=baseline, file_findings=findings)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        run(args)
    except InputError as exc:
        print("Scanner: " + str(exc), file=sys.stderr)
        return 2
    except Exception:
        # Never print driver/parser/OS exceptions: they can include a DSN, SQL
        # literals, file content, or row values. No traceback in the public CLI.
        print("Scanner gagal. Periksa koneksi, izin baca, konfigurasi, dan format input. Detail sumber disembunyikan untuk menjaga data.", file=sys.stderr)
        return 2
    print("Selesai. Hasil termasking telah ditulis.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
