import csv

import pytest

from scanner.evaluation import evaluate
from scanner.sources import InputError


def write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_metrics(tmp_path):
    truth, pred = tmp_path / "truth.csv", tmp_path / "pred.csv"
    fields = ["table", "column", "is_personal", "detected_type", "pdp_class"]
    rows = [dict(zip(fields, ["t", "a", "1", "email", "umum"])),
            dict(zip(fields, ["t", "b", "0", "operasional", "non_pribadi"])),
            dict(zip(fields, ["t", "c", "1", "nama", "umum"])),
            dict(zip(fields, ["t", "d", "0", "operasional", "non_pribadi"]))]
    write_csv(truth, fields, rows)
    predictions = [dict(r) for r in rows[:2] + rows[3:]]
    predictions[1]["pdp_class"] = "umum"
    write_csv(pred, fields, predictions)
    result = evaluate(pred, truth)
    assert result["precision"] == result["recall"] == result["f1"] == 0.5
    assert result["confusion_matrix"] == {"tp": 1, "fp": 1, "fn": 1, "tn": 1}
    assert result["detected_type_accuracy"] == 0.75
    assert result["pdp_class_accuracy"] == 0.5
    assert result["false_positive"] == [{"table": "t", "column": "b"}]
    assert result["false_negative"] == [{"table": "t", "column": "c"}]


def test_empty_ground_truth_rejected(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("table,column,is_personal,detected_type,pdp_class\n")
    with pytest.raises(InputError):
        evaluate(path, path)
