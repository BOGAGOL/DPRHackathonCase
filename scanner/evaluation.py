import csv

from .sources import InputError


def evaluate(pred_path, truth_path):
    def load(path, required):
        with open(path, encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not required.issubset(reader.fieldnames or []):
                raise InputError("Header CSV evaluasi tidak sesuai.")
            result = {}
            for row in reader:
                key = row["table"], row["column"]
                if key in result:
                    raise InputError("Kunci tabel/kolom duplikat dalam CSV evaluasi.")
                result[key] = row
            return result
    predictions = load(pred_path, {"table", "column", "pdp_class", "detected_type"})
    truth = load(truth_path, {"table", "column", "is_personal", "detected_type", "pdp_class"})
    if not truth:
        raise InputError("Ground truth kosong; isi secara manual sebelum evaluasi.")
    tp = fp = fn = tn = correct_type = correct_class = 0
    false_positive, false_negative, missing = [], [], []
    type_matrix, class_matrix = {}, {}
    for key, actual in truth.items():
        if actual["is_personal"].strip().lower() not in {"1", "0", "true", "false", "yes", "no"}:
            raise InputError("is_personal harus 1/0, true/false, atau yes/no.")
        positive = actual["is_personal"].strip().lower() in {"1", "true", "yes"}
        pred = predictions.get(key)
        # Low confidence is still a candidate, never silently treated as negative.
        predicted = pred is not None and pred["pdp_class"] != "non_pribadi"
        entry = {"table": key[0], "column": key[1]}
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
        for field, matrix in (("detected_type", type_matrix), ("pdp_class", class_matrix)):
            expected = actual[field]
            observed = pred[field] if pred else "missing_prediction"
            matrix.setdefault(expected, {})[observed] = matrix.setdefault(expected, {}).get(observed, 0) + 1
        correct_type += bool(pred and pred["detected_type"] == actual["detected_type"])
        correct_class += bool(pred and pred["pdp_class"] == actual["pdp_class"])
    precision, recall = tp / (tp + fp) if tp + fp else 0, tp / (tp + fn) if tp + fn else 0
    return {"evaluation_stage": "raw_before_human_review", "is_personal_rule": "pdp_class != non_pribadi (including low_confidence)",
            "precision": precision, "recall": recall, "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0,
            "detected_type_accuracy": correct_type / len(truth), "pdp_class_accuracy": correct_class / len(truth),
            "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
            "detected_type_confusion_matrix": type_matrix, "pdp_class_confusion_matrix": class_matrix,
            "false_positive": false_positive, "false_negative": false_negative, "missing_predictions": missing,
            "truth_rows": len(truth), "prediction_rows": len(predictions),
            "unlabelled_predictions": [{"table": k[0], "column": k[1]} for k in predictions.keys() - truth.keys()]}
