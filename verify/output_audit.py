"""Bounded exact-field output audit, explicitly not an operational S06 scan."""
import argparse
import csv
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path

from benchmark.common import ROOT, utc_now, write_json
from .known_values import KnownValues
from .profile import SENSITIVE


class TextFields(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fields = set()

    def handle_data(self, data):
        self.fields.add(unescape(data).strip())


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings(child)


def audit(known, files):
    exported = set()
    public_metadata_exceptions = []
    for path in files:
        if path.suffix == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            # This date is fixed by the public experimental methodology. It may
            # coincidentally equal some marriage dates; exempt only this field,
            # never that value elsewhere (especially inventory/sample fields).
            if path.name == "residual_before.json" and payload.get("age_band", {}).get("reference_date") == "2026-10-01":
                del payload["age_band"]["reference_date"]
                public_metadata_exceptions.append({"file": path.name, "field": "age_band.reference_date",
                                                   "reason": "public fixed methodological reference date, not a recovered row"})
            exported.update(strings(payload))
        elif path.suffix == ".csv":
            with path.open(encoding="utf-8", newline="") as handle:
                exported.update(cell for row in csv.reader(handle) for cell in row)
        elif path.suffix == ".html":
            parser = TextFields()
            parser.feed(path.read_text(encoding="utf-8"))
            exported.update(parser.fields)
    exposed, checked, rows = {}, 0, 0
    columns = ",".join('"' + c + '"' for c in SENSITIVE)
    for row in known.connection.execute("SELECT " + columns + " FROM known"):
        rows += 1
        for column, value in zip(SENSITIVE, row):
            if value is not None and len(value) >= 6:
                checked += 1
                if value in exported:
                    exposed[column] = exposed.get(column, 0) + 1
    return {"status": "PASSED" if not exposed else "FAILED", "timestamp_utc": utc_now(),
            "files_checked": [p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else p.name for p in files],
            "known_rows": rows, "non_null_sensitive_cells_length_at_least_6_checked": checked,
            "exact_unmasked_field_matches_by_column": exposed,
            "public_metadata_exceptions": public_metadata_exceptions,
            "method": "hash-set equality against JSON primitive strings, CSV fields and HTML text nodes",
            "limitations": ["Only enumerated evidence outputs; not repo history, logs, WAL or secret scanning.",
                            "Does not search arbitrary embedded substrings or short categorical values; not a full S06 claim."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--known-values", type=Path, required=True)
    args = parser.parse_args()
    files = sorted([*ROOT.glob("evidence/leak/**/*.json"), *ROOT.glob("evidence/leak/**/*.csv"),
                    *ROOT.glob("evidence/leak/**/*.html"), *ROOT.glob("evidence/leakage/*.json"),
                    *ROOT.glob("evidence/leakage/*.csv"), ROOT / "evidence/benchmark/runner_overhead.json"])
    # Avoid scanning the previous audit result into its own denominator.
    files = [p for p in files if p.name != "output_privacy_audit.json"]
    known = KnownValues(args.known_values)
    try:
        report = audit(known, files)
        write_json(ROOT / "evidence/leak/output_privacy_audit.json", report)
        if report["status"] != "PASSED":
            raise SystemExit("Evidence contains an exact known value; details withheld")
        print(json.dumps({"status": report["status"], "files": len(files), "rows": report["known_rows"]}))
    finally:
        known.close()


if __name__ == "__main__":
    main()
