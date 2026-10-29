"""Exact small projections via hash counters, including visible NULL patterns."""
from collections import Counter
from datetime import date
from itertools import combinations

from .profile import REF, SENSITIVE

REFERENCE_DATE = date(2026, 10, 1)


def age_band(value):
    if value is None:
        return None
    born = date.fromisoformat(str(value))
    if born > REFERENCE_DATE:
        raise ValueError("Birth date after fixed reference date")
    age = REFERENCE_DATE.year - born.year - ((REFERENCE_DATE.month, REFERENCE_DATE.day) < (born.month, born.day))
    lower = age // 10 * 10
    return f"{lower}-{lower + 9}"


def group_metrics(counts, columns):
    total = sum(counts.values())
    unique = sum(1 for n in counts.values() if n == 1)
    return {"columns": list(columns), "total_rows": total, "groups": len(counts), "unique_rows": unique,
            "unique_ratio": unique / total if total else None, "k_min": min(counts.values(), default=0)}


class BeforeAggregation:
    def __init__(self):
        self.joint = {g: Counter() for g in ("all", "source_734", "synthetic")}
        self.birth = {g: Counter() for g in self.joint}
        self.null_counts = Counter()
        self.rows = 0

    def add(self, row):
        nulls = tuple(row[c] is None for c in SENSITIVE)
        projection = tuple(row[c] for c in REF) + (age_band(row["tanggal_lahir"]),) + nulls
        birth = (row["tempat_lahir"], row["tanggal_lahir"], row["jenis_kelamin"])
        scope = "source_734" if int(row["id"]) <= 734 else "synthetic"
        for group in ("all", scope):
            self.joint[group][projection] += 1
            self.birth[group][birth] += 1
        self.null_counts.update(c for c in SENSITIVE if row[c] is None)
        self.rows += 1

    def results(self):
        # Constant indicators cannot refine any group. Record rather than repeat
        # thousands of equivalent 1-3 attribute combinations involving constants.
        variable = [c for c in SENSITIVE if 0 < self.null_counts[c] < self.rows]
        omitted = [c for c in SENSITIVE if c not in variable]
        names = list(REF) + ["age_band"] + ["is_null_" + c for c in variable]
        indices = list(range(5)) + [5 + SENSITIVE.index(c) for c in variable]
        output = {}
        for scope, joint in self.joint.items():
            results = []
            for size in (1, 2, 3):
                for combo in combinations(range(len(names)), size):
                    projected = Counter()
                    for key, count in joint.items():
                        projected[tuple(key[indices[i]] for i in combo)] += count
                    results.append(group_metrics(projected, [names[i] for i in combo]))
            output[scope] = {"combinations": results,
                             "birth_reference": group_metrics(self.birth[scope], ("tempat_lahir", "tanggal_lahir", "jenis_kelamin"))}
        return {"method": "exact hash-counter projection of full artifact, no row/group values exported",
                "age_band": {"reference_date": str(REFERENCE_DATE), "width_years": 10,
                             "before_storage": "virtual projection; actual birth date remains plaintext in baseline"},
                "attributes": names, "omitted_constant_null_indicators": omitted,
                "constant_null_counts": {c: self.null_counts[c] for c in omitted},
                "constant_omission_reason": "Adding a constant never changes groups, unique rows or k_min",
                "null_policy": "NULL forms a group; indicators represent every contract AEAD column",
                "populations": output}
