from collections import Counter
from datetime import date
import random

import pytest

from datagen.model import (CATEGORICAL, UNIQUE, anniversary, canonical, checksum, generate,
                           learn, marriage_kind, number_stream, validate)


def test_anniversary_and_marriage_boundaries(source):
    assert anniversary(date(2000, 2, 29), 17) == date(2017, 2, 28)
    row = dict(source[0], tanggal_lahir=date(2000, 1, 1))
    for when, kind in [(None, "null"), (date(1999, 1, 1), "before_birth"),
                       (date(2016, 12, 31), "under_17"), (date(2017, 1, 1), "adult")]:
        assert marriage_kind(dict(row, tanggal_pernikahan=when)) == kind


def test_canonical_digest_preserves_null_zero_order(source):
    assert b"null" in canonical(source[1])
    assert checksum(source) != checksum(list(reversed(source)))
    changed = [dict(r) for r in source]
    changed[0]["no_ktp"] = str(int(changed[0]["no_ktp"]))
    assert checksum(source) != checksum(changed)


def test_permutation_skips_occupied_and_reports_exhaustion():
    stream = number_stream("0", 2, random.Random(42), {"01", "02"})
    result = [next(stream) for _ in range(8)]
    assert len(set(result)) == 8 and not {"01", "02"}.intersection(result)
    with pytest.raises(ValueError, match="exhausted"):
        next(stream)


def test_deterministic_2000_rows_and_source_preservation(source):
    first = list(generate(source, 2000, 42))
    assert checksum(first) == checksum(generate(source, 2000, 42))
    assert checksum(first) != checksum(generate(source, 2000, 43))
    assert first[:len(source)] == source
    assert all(len({r[c] for r in first}) == len(first) for c in UNIQUE)
    assert validate(first, source, 2000)["passed"]


def test_complete_template_cycles_preserve_joint_distribution_and_anomalies(source):
    rows = list(generate(source, len(source) * 11))
    additional = rows[len(source):]
    for col in CATEGORICAL:
        assert Counter(r[col] for r in additional) == Counter({k: v * 10 for k, v in Counter(r[col] for r in source).items()})
    assert Counter(map(marriage_kind, additional)) == Counter({k: v * 10 for k, v in Counter(map(marriage_kind, source)).items()})
    assert validate(rows, source, len(rows))["anomaly_policy_valid"]


def test_no_anomalies_changes_only_additional_population(source):
    rows = list(generate(source, 2000, replicate_anomalies=False))
    report = validate(rows, source, 2000, replicate_anomalies=False)
    assert rows[:40] == source and report["passed"]
    assert all(marriage_kind(r) in {"null", "adult"} for r in rows[40:])
    assert report["anomalies"]["source"]["before_birth"] > 0


@pytest.mark.parametrize("fault", ["format", "duplicate", "relation", "source", "distribution", "anomalies", "count"])
def test_validation_rejects_mutation_without_exporting_values(source, fault):
    rows = list(generate(source, 2000))
    if fault == "format":
        rows[40]["npwp"] = "invalid-sensitive-value"
    elif fault == "duplicate":
        rows[40]["email"] = rows[41]["email"]
    elif fault == "relation":
        rows[40]["jumlah_jiwa"] = -1
    elif fault == "source":
        rows[0]["nama"] = "invalid-sensitive-value"
    elif fault == "distribution":
        for row in rows[40:]:
            row["jenis_kelamin"] = "P"
    elif fault == "anomalies":
        for row in rows[40:]:
            if row["tanggal_pernikahan"]:
                row["tanggal_pernikahan"] = row["tanggal_lahir"]
    else:
        rows.pop()
    report = validate(rows, source, 2000)
    assert not report["passed"]
    assert "invalid-sensitive-value" not in str(report)
    assert not any(r["email"] in str(report) for r in source)


def test_learning_and_input_guards(source):
    assert learn(source)["birth_min"] == date(1970, 1, 1)
    with pytest.raises(ValueError):
        learn([])
    with pytest.raises(ValueError):
        learn([{"id": 1}])
    with pytest.raises(ValueError):
        learn([dict(source[0], tanggal_lahir=date(2100, 1, 1))])
    with pytest.raises(ValueError):
        list(generate(source, 1))
    with pytest.raises(ValueError):
        list(generate(source + [source[0]], 100))
