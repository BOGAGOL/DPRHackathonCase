import csv
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import CHANGE_SUMMARY, __version__
from .detection import DICTIONARIES, classify, name_scores, valid_date
from .model import INVENTORY_FIELDS
from .relations import relationships


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def conditional_date_presence(table, index, config):
    values = [row[index] for row in table.rows]
    nonnull = [str(v) for v in values if v is not None and str(v).strip()]
    if not nonnull or len(nonnull) == len(values) or not all(valid_date(v) for v in nonnull):
        return None
    sources, marital_context = [], False
    for source_index, column in enumerate(table.columns):
        if source_index == index:
            continue
        rows = [row for row in table.rows if row[source_index] is not None]
        counts = Counter(str(row[source_index]) for row in rows)
        if len(rows) < config["minimum_relation_rows"] or not 1 < len(counts) <= 12:
            continue
        best = max(sum((str(row[source_index]) == category) == (row[index] is not None and str(row[index]).strip() != "")
                       for row in rows) for category in counts)
        if best / len(rows) >= config["relation_threshold"]:
            sources.append(column)
            marital_context |= bool(name_scores(column)["status_perkawinan"])
    return {"source_columns": sources, "marital_context": marital_context} if sources else None


def ordered_anonymity(anonymity):
    return sorted(anonymity, key=lambda r: (len(r["columns"]), -r["unique_rows"], r["table"], tuple(r["columns"])))


def minimal_anonymity(anonymity):
    """Suppress supersets in presentation only; retain every result in JSON."""
    shown, already_unique = [], {}
    for row in ordered_anonymity(anonymity):
        columns = frozenset(row["columns"])
        bases = already_unique.setdefault(row["table"], [])
        if any(base < columns for base in bases):
            continue
        shown.append(row)
        if row["total_rows"] and row["unique_rows"] / row["total_rows"] >= 0.95:
            bases.append(columns)
    return shown


def annotate_birth_uniqueness(inventory, anonymity):
    singles = {(row["table"], row["columns"][0]): row for row in anonymity if len(row["columns"]) == 1}
    for row in inventory:
        if row["detected_type"] != "tanggal_lahir":
            continue
        result = singles.get((row["table"], row["column"]))
        note = (f"k-anonymity satu kolom: {result['unique_rows']} dari {result['total_rows']} baris unik (k=1)"
                if result else "k-anonymity satu kolom belum tersedia untuk sumber ini")
        if note not in row["reason"]:
            row["reason"] += "; " + note


def analyze(tables, config, environment, baseline=False):
    inventory, all_features = [], {}
    for table in tables:
        bank_context = any(str(v).strip().lower() in DICTIONARIES["bank"]
                           for row in table.rows for v in row if v is not None)
        for index, column in enumerate(table.columns):
            row, f = classify(column, [r[index] for r in table.rows], config, environment,
                              bank_context=bank_context, baseline=baseline, data_type=table.data_types[index],
                              conditional_presence=conditional_date_presence(table, index, config) if not baseline else None)
            row.update(table=table.name, column=column, data_type=table.data_types[index])
            inventory.append(row)
            all_features[(table.name, column)] = f
    rels = relationships(tables, inventory, config)
    return inventory, all_features, rels


def emit(out, inventory, feature_map, relations, anonymity, *, label, source, sample, duration, baseline=False, file_findings=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    anonymity = ordered_anonymity(anonymity)
    annotate_birth_uniqueness(inventory, anonymity)
    with (out / "inventory.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=INVENTORY_FIELDS)
        writer.writeheader()
        writer.writerows(inventory)
    write_json(out / "features.json", [{"table": table, "column": column, **f}
                                       for (table, column), f in feature_map.items()])
    write_json(out / "relations.json", relations)
    write_json(out / "k_anonymity.json", anonymity)
    meta = {"label": label, "timestamp": datetime.now(timezone.utc).isoformat(), "scanner_version": __version__,
            "change_summary": CHANGE_SUMMARY,
            "source": source, "sample_limit_per_table": sample, "duration_seconds": round(duration, 3),
            "method": "regex_only" if baseline else "combined", "review_state": "raw_before_human_review",
            "inventory_columns": len(inventory), "table_counts": source.get("table_counts", {}),
            "privacy": "Only masked samples and aggregate features are exported."}
    write_json(out / "run_meta.json", meta)
    if file_findings is not None:
        with (out / "findings.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["file", "line", "detected_type", "sample_masked"])
            writer.writeheader()
            writer.writerows(file_findings)
    env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"),
                      autoescape=select_autoescape(["html"]))
    report = env.get_template("report.html").render(inventory=inventory, fields=INVENTORY_FIELDS,
              review=[r for r in inventory if r["triage"] == "needs_review"], relations=relations,
              anonymity=minimal_anonymity(anonymity)[:15], anonymity_total=len(anonymity),
              meta=meta, findings=file_findings or [])
    (out / "report.html").write_text(report, encoding="utf-8")
    return meta
