"""Generic relationships over aligned sample rows, never exported values."""
from collections import Counter
from decimal import Decimal, InvalidOperation
from itertools import combinations

from .masking import mask, normalize

PROTECTION_NOTE = "perlakuan masking/akses harus konsisten dengan kolom sumber, jika tidak kontrol dapat dilewati"


def numeric(value):
    try:
        return Decimal(str(value)) if value is not None else None
    except InvalidOperation:
        return None


def relationships(tables, inventory, config):
    by_key = {(r["table"], r["column"]): r for r in inventory}
    derived, dependencies, joins, near_unique = [], [], [], []
    threshold, minimum = config["relation_threshold"], config["minimum_relation_rows"]
    for table in tables:
        source_unique_ratios = {}
        for index, column in enumerate(table.columns):
            nonnull = [str(r[index]) for r in table.rows if r[index] is not None and str(r[index]).strip()]
            ratio = len(set(nonnull)) / max(1, len(nonnull))
            source_unique_ratios[index] = ratio
            if ratio > 0.8:
                near_unique.append({"table": table.name, "column": column, "unique_ratio": ratio,
                                    "unique_values": len(set(nonnull)), "nonnull_rows": len(nonnull),
                                    "sample_rows": len(table.rows), "excluded_from": "functional_source",
                                    "reason": "rasio unik non-NULL > 0.8; korelasi tidak membuktikan dependency"})
        for a, b in combinations(range(len(table.columns)), 2):
            ca, cb = table.columns[a], table.columns[b]
            pairs = [(r[a], r[b]) for r in table.rows if r[a] is not None and r[b] is not None
                     and str(r[a]).strip() and str(r[b]).strip()]
            if len(pairs) < minimum:
                continue
            normalized = [(normalize(x), normalize(y)) for x, y in pairs]
            # Text relationships require varied values; single categories/numeric counters
            # do not establish a useful duplicate identity relation.
            if min(len({x for x, _ in normalized}), len({y for _, y in normalized})) >= minimum:
                textual = [(x, y) for x, y in normalized if len(x) >= 3 and len(y) >= 3 and
                           any(c.isalpha() for c in x) and any(c.isalpha() for c in y)]
                if len(textual) >= minimum:
                    predicates = {
                        "equal": sum(x == y for x, y in textual),
                        "a_prefix_b": sum(y.startswith(x) for x, y in textual),
                        "b_prefix_a": sum(x.startswith(y) for x, y in textual),
                        "a_in_b": sum(x in y for x, y in textual),
                        "b_in_a": sum(y in x for x, y in textual),
                    }
                    for relation, hits in predicates.items():
                        ratio = hits / len(pairs)
                        if ratio < threshold:
                            continue
                        if relation == "equal":
                            source, target = sorted((ca, cb), key=lambda c: (
                                by_key[(table.name, c)]["detected_type"] != "nama", len(c), c))
                        else:
                            # Prefer the person-name candidate as source, even when
                            # an account-holder field is a truncated version of it.
                            ra, rb = by_key[(table.name, ca)], by_key[(table.name, cb)]
                            if ra["detected_type"] == "nama" and rb["detected_type"] != "nama":
                                source, target = ca, cb
                            elif rb["detected_type"] == "nama" and ra["detected_type"] != "nama":
                                source, target = cb, ca
                            elif ra["detected_type"] == rb["detected_type"] == "nama":
                                source, target = sorted((ca, cb), key=lambda c: (len(c), c))
                            else:
                                source, target = (ca, cb) if relation.startswith("a_") else (cb, ca)
                        record = {"table": table.name, "source": source, "column": target,
                                  "relation": relation, "a": ca, "b": cb,
                                  "ratio": round(ratio, 6), "compared_rows": len(pairs),
                                  "implication": "Melindungi kolom sumber saja tidak cukup; tinjau turunan dan minimisasi."}
                        derived.append(record)
                        target_row = by_key[(table.name, target)]
                        sources = set(filter(None, target_row["derived_from"].split(";")))
                        sources.add(source)
                        target_row["derived_from"] = ";".join(sorted(sources))
                        target_row["consistent_protection_with"] = target_row["derived_from"]
                        if target_row["recommendation"] != "hash":
                            target_row["recommendation"] = "review_minimization"
                        if PROTECTION_NOTE not in target_row["reason"]:
                            target_row["reason"] += "; " + PROTECTION_NOTE
                        break
            numbers = [(numeric(x), numeric(y)) for x, y in pairs]
            numbers = [(x, y) for x, y in numbers if x is not None and y is not None and x.is_finite() and y.is_finite()]
            if len(numbers) >= minimum and len({x for x, _ in numbers}) >= 3:
                offsets = Counter(y - x for x, y in numbers)
                offset, hits = offsets.most_common(1)[0]
                if hits / len(pairs) >= threshold:
                    # Offsets are relationship constants, not source row values.
                    dependencies.append({"table": table.name, "kind": "arithmetic_offset",
                                         "source": ca, "target": cb, "offset": str(offset),
                                         "ratio": hits / len(pairs), "compared_rows": len(pairs)})
            # A verified text component can explain a relation even when the complete
            # source is unique. This is recorded separately from group-based FD.
            for source_i, target_i in ((a, b), (b, a)):
                oriented = pairs if source_i == a else [(y, x) for x, y in pairs]
                if (minimum <= len({str(y) for _, y in oriented}) <= 0.8 * len(oriented)
                        and all("," in str(x) for x, _ in oriented)):
                    hits = sum(normalize(str(x).rsplit(",", 1)[-1]) == normalize(y) for x, y in oriented)
                    if hits == len(oriented):
                        dependencies.append({"table": table.name, "kind": "text_component",
                            "source": table.columns[source_i], "target": table.columns[target_i],
                            "component": "last_comma_segment", "ratio": 1.0, "compared_rows": len(oriented),
                            "basis": "matched extracted component; no inference from unique full source values"})
            # Functional dependency via exact group consistency: no category values exported.
            for source_i, target_i in ((a, b), (b, a)):
                if source_unique_ratios[source_i] > 0.8:
                    continue
                groups = {}
                for row in table.rows:
                    if row[source_i] is not None:
                        groups.setdefault(str(row[source_i]), set()).add(str(row[target_i]))
                if len(groups) > 1:
                    consistent = sum(len(v) == 1 for v in groups.values()) / len(groups)
                    if consistent == 1.0:
                        dependencies.append({"table": table.name, "kind": "functional",
                                             "source": table.columns[source_i], "target": table.columns[target_i],
                                             "consistent_group_ratio": consistent, "groups": len(groups)})
            # Presence iff a category: evaluate both directions including NULL rows.
            for category_i, nullable_i in ((a, b), (b, a)):
                rows = [r for r in table.rows if r[category_i] is not None]
                counts = Counter(str(r[category_i]) for r in rows)
                if not 1 < len(counts) <= 12 or len(rows) < minimum:
                    continue
                present = [r[nullable_i] is not None and str(r[nullable_i]).strip() != "" for r in rows]
                if not any(present) or all(present):
                    continue
                best = max((sum((str(r[category_i]) == value) == exists for r, exists in zip(rows, present)), value)
                           for value in counts)
                if best[0] / len(rows) >= threshold:
                    dependencies.append({"table": table.name, "kind": "presence_iff_category",
                                         "source": table.columns[category_i], "target": table.columns[nullable_i],
                                         "category_masked": mask(best[1]), "ratio": best[0] / len(rows),
                                         "compared_rows": len(rows)})
    attempted = 0
    truncated = False
    for left, right in combinations(tables, 2):
        for ai, ac in enumerate(left.columns):
            for bi, bc in enumerate(right.columns):
                if attempted >= config["max_join_pairs"]:
                    truncated = True
                    break
                attempted += 1
                av = {normalize(r[ai]) for r in left.rows if r[ai] is not None}
                bv = {normalize(r[bi]) for r in right.rows if r[bi] is not None}
                av.discard("")
                bv.discard("")
                if min(len(av), len(bv)) < minimum:
                    continue
                ratio = len(av & bv) / min(len(av), len(bv))
                if ratio >= threshold:
                    joins.append({"left_table": left.name, "left_column": ac, "right_table": right.name,
                                  "right_column": bc, "overlap_ratio": ratio, "basis": "sample_values",
                                  "confirmed": False})
    return {"derived_from": derived, "dependencies": dependencies, "join_candidates": joins,
            "near_unique_quasi_identifiers": near_unique,
            "functional_policy": {"maximum_source_unique_ratio": 0.8, "required_consistent_group_ratio": 1.0,
                                  "source_ratio_denominator": "non-NULL sample rows"},
            "join_pairs_checked": attempted, "join_limit_reached": truncated,
            "scope": "sample; correlations are candidates requiring human review"}


def quasi_combinations(table, column_features, config):
    candidates = []
    for index, col in enumerate(table.columns):
        f = column_features[(table.name, col)]
        semantic = f["semantic_candidate"]
        distinct = len({str(r[index]) for r in table.rows if r[index] is not None})
        preferred = semantic in {"tanggal_lahir", "tanggal_pernikahan", "tempat_lahir", "jenis_kelamin", "agama", "status_perkawinan"}
        # Generic low/medium cardinality candidates include jobs, locations, and
        # date columns even with disguised names. Unique direct IDs are excluded.
        if f["nonnull"] and (preferred or 1 < distinct <= max(2, len(table.rows) * 0.5)):
            candidates.append((not preferred, index))
    indices = [i for _, i in sorted(candidates)[:config["max_quasi_candidates"]]]
    result = []
    for size in (1, 2, 3):
        for combo in combinations(indices, size):
            if len(result) >= config["max_combinations"]:
                return result
            result.append(combo)
    return result


def k_summary(table, columns, counts, total, scope):
    counts = list(counts)
    return {"table": table.name, "columns": [table.columns[i] for i in columns],
            "total_rows": total, "unique_rows": sum(n == 1 for n in counts),
            "k_min": min(counts, default=0), "groups": len(counts), "scope": scope,
            "null_policy": "NULL values form a group; no row values exported"}


def memory_k(table, combos):
    return [k_summary(table, combo, Counter(tuple(r[i] for i in combo) for r in table.rows).values(),
                      len(table.rows), "full_fixture") for combo in combos]
