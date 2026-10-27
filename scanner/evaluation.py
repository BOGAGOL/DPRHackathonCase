"""Evaluate frozen predictions without changing labels or importing data values."""
import csv
import hashlib
import json
import math
from pathlib import Path

import yaml

from .sources import InputError

CONFIG = Path(__file__).parent / "config" / "label_map.yaml"


def normalize_personal(value):
    token = str(value).strip().lower()
    if token not in {"1", "0", "true", "false", "yes", "no"}:
        raise InputError("is_personal harus 1/0, true/false, atau yes/no.")
    return token in {"1", "true", "yes"}


def normalize_class(value):
    token = str(value).strip().lower().replace("-", "_")
    if token not in {"umum", "spesifik", "non_pribadi"}:
        raise InputError("Kelas PDP evaluasi tidak dikenali.")
    return token


def column_key(table, column):
    table, column = table.strip(), column.strip()
    if not table or not column:
        raise InputError("Nama tabel/kolom evaluasi kosong.")
    return (table if "." in table else "public." + table), column


def load_rows(path, required):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not required.issubset(reader.fieldnames or []):
            raise InputError("Header CSV evaluasi tidak sesuai.")
        result = {}
        for row in reader:
            if any(row.get(field) is None for field in required):
                raise InputError("Baris CSV evaluasi tidak lengkap.")
            key = column_key(row["table"], row["column"])
            if key in result:
                raise InputError("Kunci tabel/kolom duplikat dalam CSV evaluasi.")
            result[key] = row
        return result


def load_label_map(path=None):
    config = yaml.safe_load(Path(path or CONFIG).read_text(encoding="utf-8"))
    if (not isinstance(config, dict) or config.get("version") != 1
            or not isinstance(config.get("native_types"), list)
            or not isinstance(config.get("labels"), dict)
            or not isinstance(config.get("regex_only"), dict)):
        raise InputError("Konfigurasi label map tidak sesuai.")
    native = config["native_types"]
    baseline = config["regex_only"]
    if (not native or not all(isinstance(value, str) and value for value in native)
            or not all(isinstance(key, str) and value in native for key, value in config["labels"].items())
            or not isinstance(baseline.get("personal_types"), list)
            or not set(baseline["personal_types"]).issubset(native)
            or type(baseline.get("min_content_score")) not in (int, float)
            or not 0 <= baseline["min_content_score"] <= 100):
        raise InputError("Isi label map atau aturan regex_only tidak sesuai.")
    return config


def mapped_type(label, config):
    label = label.strip()
    if label.lower() in config["native_types"]:
        return label.lower()
    return config["labels"].get(label.upper())


def evaluate(pred_path, truth_path, label_map_path=None, baseline=None):
    config = load_label_map(label_map_path)
    predictions = load_rows(pred_path, {"table", "column", "pdp_class", "detected_type"})
    truth = load_rows(truth_path, {"table", "column", "is_personal", "detected_type", "pdp_class"})
    if not truth:
        raise InputError("Ground truth kosong; isi secara manual sebelum evaluasi.")
    meta_path = Path(pred_path).parent / "run_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8-sig")) if meta_path.is_file() else {}
    method = baseline or meta.get("method", "combined")
    if method not in {"combined", "regex_only"} or (baseline and meta.get("method", baseline) != baseline):
        raise InputError("Metode evaluasi bertentangan dengan metadata prediksi.")
    tp = fp = fn = tn = correct_type = correct_class = 0
    false_positive, false_negative, missing, mismatches, unmapped = [], [], [], [], []
    type_matrix, class_matrix = {}, {}
    for key, actual in truth.items():
        positive = normalize_personal(actual["is_personal"])
        expected_class = normalize_class(actual["pdp_class"])
        expected_type = mapped_type(actual["detected_type"], config)
        pred = predictions.get(key)
        entry = {"table": actual["table"].strip(), "column": actual["column"].strip()}
        observed_class = normalize_class(pred["pdp_class"]) if pred else "missing_prediction"
        observed_type = mapped_type(pred["detected_type"], config) if pred else "missing_prediction"
        for source, row, mapped in (("truth", actual, expected_type), ("prediction", pred, observed_type)):
            if row is not None and mapped is None:
                unmapped.append({**entry, "source": source, "label": row["detected_type"]})
        predicted = pred is not None and observed_class != "non_pribadi"
        if method == "regex_only" and pred is not None:
            try:
                score, name_score = float(pred["content_score"]), float(pred["name_score"])
            except (KeyError, TypeError, ValueError):
                raise InputError("regex_only memerlukan content_score dan name_score numerik.") from None
            if not math.isfinite(score) or not 0 <= score <= 100 or name_score != 0:
                raise InputError("Prediksi regex_only harus murni isi, tanpa skor nama.")
            predicted = (observed_type in config["regex_only"]["personal_types"]
                         and score >= config["regex_only"]["min_content_score"])
        if positive and predicted:
            tp += 1
        elif not positive and predicted:
            fp += 1
            false_positive.append(entry)
        elif positive:
            fn += 1
            false_negative.append(entry)
        else:
            tn += 1
        if pred is None:
            missing.append(entry)
        expected_type_cell = expected_type or "unmapped_truth:" + actual["detected_type"]
        observed_type_cell = observed_type or "unmapped_prediction:" + pred["detected_type"]
        for expected, observed, matrix in ((expected_type_cell, observed_type_cell, type_matrix),
                                            (expected_class, observed_class, class_matrix)):
            matrix.setdefault(expected, {})[observed] = matrix.setdefault(expected, {}).get(observed, 0) + 1
        type_ok = bool(pred and expected_type is not None and observed_type == expected_type)
        class_ok = bool(pred and observed_class == expected_class)
        correct_type += type_ok
        correct_class += class_ok
        if not type_ok or not class_ok or positive != predicted:
            mismatches.append({**entry,
                "expected": {"is_personal": positive, "detected_type": expected_type_cell, "pdp_class": expected_class},
                "predicted": {"is_personal": predicted, "detected_type": observed_type_cell, "pdp_class": observed_class},
                "fields": [field for field, ok in (("is_personal", positive == predicted),
                           ("detected_type", type_ok), ("pdp_class", class_ok)) if not ok]})
    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    unlabelled = [{"table": predictions[k]["table"].strip(), "column": predictions[k]["column"].strip()}
                  for k in sorted(predictions.keys() - truth.keys())]
    return {"evaluation_stage": "raw_before_human_review", "in_sample": True, "method": method,
            "scanner_version": meta.get("scanner_version", "not_recorded"),
            "is_personal_rule": ("regex content_score >= configured threshold and supported regex type; absence is not proof of non-personal data"
                                 if method == "regex_only" else "pdp_class != non_pribadi (including low_confidence)"),
            "regex_only_rule": config["regex_only"] if method == "regex_only" else None,
            "precision": precision, "recall": recall,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0,
            "f2": 5 * tp / (5 * tp + fp + 4 * fn) if 5 * tp + fp + 4 * fn else 0,
            "detected_type_accuracy": correct_type / len(truth), "pdp_class_accuracy": correct_class / len(truth),
            "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
            "detected_type_confusion_matrix": type_matrix, "pdp_class_confusion_matrix": class_matrix,
            "false_positive": false_positive, "false_negative": false_negative, "missing_predictions": missing,
            "mismatches": mismatches, "unmapped_labels": unmapped, "all_labels_mapped": not unmapped,
            "truth_rows": len(truth), "prediction_rows": len(predictions),
            "evaluated_prediction_rows": len(truth.keys() & predictions.keys()),
            "unlabelled_predictions": unlabelled, "unlabelled_predictions_excluded": True,
            "input_sha256": {"predictions": hashlib.sha256(Path(pred_path).read_bytes()).hexdigest(),
                             "ground_truth": hashlib.sha256(Path(truth_path).read_bytes()).hexdigest(),
                             "label_map": hashlib.sha256(Path(label_map_path or CONFIG).read_bytes()).hexdigest()}}
