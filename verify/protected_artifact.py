"""Actual protected-dump leakage with isolated, domain-restricted attacker tokens."""

import argparse
import base64
from collections import Counter
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import time
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
import yaml

from benchmark.common import ROOT, file_hash, require_disk_space, utc_now, write_json
from datagen.model import COLUMNS
from dprcrypto import decrypt, index_message
from dprcrypto.openbao import validate_dek, validate_wrapped
from scanner.sources import copy_unescape
from .artifacts import expand_dump, private_path
from .known_values import KnownValues
from .leakage_budget import ratio
from .profile import DIRECT, FIN, PII, REF, SENSITIVE, protection_plan
from .residual import BeforeAggregation, age_band

POLICIES = {"protected_dump_with_pii_key": "modc-leak-pii",
            "protected_dump_with_finance_key": "modc-leak-finance",
            "protected_dump_with_search_key": "modc-leak-search"}
SCENARIOS = ("protected_dump_no_key", *POLICIES)
SEARCH = ("no_ktp", "email", "pengguna")
POSITION = {column: i for i, column in enumerate(COLUMNS)}


class AttackerTransit:
    """Simulation-only ACL identities; public application client remains unchanged."""
    def __init__(self, scenario):
        self.policy = POLICIES[scenario]
        self.token = os.environ["DPR_LEAK_TOKEN"]
        address = os.environ["OPENBAO_ADDR"]
        endpoint = urlsplit(address)
        if (endpoint.scheme != "https" or not endpoint.hostname or endpoint.username or endpoint.password
                or endpoint.query or endpoint.fragment or endpoint.path not in ("", "/")):
            raise ValueError("Invalid verified Transit endpoint")
        context = ssl.create_default_context(cafile=os.environ["OPENBAO_CACERT"])
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.http = httpx.Client(base_url=address.rstrip("/") + "/v1/", verify=context, trust_env=False,
                                 follow_redirects=False, timeout=15)
        try:
            identity = self.request("auth/token/lookup-self")
            if identity["policies"] != [self.policy] or not 0 < identity["ttl"] <= identity["explicit_max_ttl"] <= 14400:
                raise ValueError("Incorrect restricted attacker identity")
        except Exception:
            self.close()
            raise

    def request(self, path, payload=None):
        response = self.http.request("GET" if payload is None else "POST", path, json=payload,
                                     headers={"X-Vault-Token": self.token, "X-Vault-Request": "true"})
        if response.status_code == 403:
            raise PermissionError("Restricted policy denied endpoint")
        if response.status_code != 200:
            raise ValueError("Transit operation failed; response withheld")
        return response.json()["data"]

    def unwrap(self, kek, wrapped):
        for value in wrapped:
            validate_wrapped(value)
        result = self.request("transit/decrypt/" + kek,
            {"batch_input": [{"ciphertext": value, "reference": str(i)} for i, value in enumerate(wrapped)]})["batch_results"]
        if len(result) != len(wrapped) or any(r.get("error") or r.get("reference") != str(i) for i, r in enumerate(result)):
            raise ValueError("Incomplete restricted unwrap batch")
        return [validate_dek(base64.b64decode(r["plaintext"], validate=True)) for r in result]

    def hmac(self, column, values):
        positions = [i for i, value in enumerate(values) if value is not None]
        if not positions:
            return [None] * len(values)
        result = self.request("transit/hmac/search-hmac/sha2-256", {"key_version": 1,
            "batch_input": [{"input": base64.b64encode(index_message(column, values[i])).decode(), "reference": str(j)}
                            for j, i in enumerate(positions)]})["batch_results"]
        if len(result) != len(positions):
            raise ValueError("Incomplete restricted HMAC batch")
        output = [None] * len(values)
        for j, (i, item) in enumerate(zip(positions, result)):
            value = item.get("hmac", "")
            if item.get("error") or item.get("reference") != str(j) or not value.startswith("vault:v1:"):
                raise ValueError("Invalid restricted HMAC response")
            digest = base64.b64decode(value.rsplit(":", 1)[1], validate=True)
            if len(digest) != 32:
                raise ValueError("Invalid restricted HMAC digest length")
            output[i] = digest
        return output

    def denied(self, kek, wrapped):
        try:
            self.unwrap(kek, [wrapped])
        except PermissionError:
            return True
        return False

    def close(self):
        self.http.close()
        self.token = ""


def protected_rows(path, profile):
    """Skip non-member COPY blocks; never execute dump SQL or use SQL substrings."""
    active, selected, tables = False, False, 0
    required = {"anggota_id", "legacy_row_id", "protection_version", "dek_pii_wrapped", "dek_fin_wrapped", "age_band"}
    required |= {c["storage_column"] for c in profile["columns"].values()}
    required |= {c["bidx_column"] for c in profile["columns"].values() if c["bidx"]}
    with path.open(encoding="utf-8", newline="") as stream:
        for line in stream:
            if active:
                raw = line.rstrip("\r\n")
                if raw == r"\.":
                    active = selected = False
                    continue
                if not selected:
                    continue
                values = raw.split("\t")
                if len(values) != len(columns):
                    raise ValueError("Truncated protected COPY row")
                row = {c: None if v == r"\N" else copy_unescape(v) for c, v in zip(columns, values)}
                for c in columns:
                    if (c.endswith("_ct") or c.endswith("_bidx")) and row[c] is not None:
                        if not row[c].startswith(r"\x"):
                            raise ValueError("Unsupported protected bytea encoding")
                        row[c] = bytes.fromhex(row[c][2:])
                row["legacy_row_id"] = int(row["legacy_row_id"])
                row["protection_version"] = int(row["protection_version"])
                yield row
            elif line.startswith("COPY "):
                header = re.fullmatch(r'COPY (.+) \((.+)\) FROM stdin;\s*', line)
                if not header:
                    raise ValueError("Unsupported COPY header")
                active = True
                selected = header[1].replace('"', '') == "public.anggota_protected"
                if selected:
                    columns = [c.strip().strip('"') for c in header[2].split(",")]
                    if not required.issubset(columns) or len(columns) != len(set(columns)):
                        raise ValueError("Protected dump columns incomplete")
                    tables += 1
    if active or tables != 1:
        raise ValueError("Missing, duplicate or truncated protected COPY table")


class AfterAggregation(BeforeAggregation):
    def add(self, row):
        projection = tuple(row[c] for c in REF) + (row["age_band"],) + tuple(row[c + "_ct"] is None for c in SENSITIVE)
        scope = "source_734" if row["legacy_row_id"] <= 734 else "synthetic"
        for group in ("all", scope):
            self.joint[group][projection] += 1
        self.null_counts.update(c for c in SENSITIVE if row[c + "_ct"] is None)
        self.rows += 1

    def results(self):
        result = super().results()
        result["age_band"]["after_storage"] = "actual plaintext age_band from protected dump"
        result["age_band"].pop("before_storage", None)
        for values in result["populations"].values():
            values.pop("birth_reference")
            values["birth_reference_status"] = "NOT_AVAILABLE: birth place/date encrypted"
        return result


def evaluate_batch(batch, expected, profile, scenario, client):
    """Batch DEK/HMAC requests and hash lookups; never per-value file searches."""
    fields = PII if scenario == "protected_dump_with_pii_key" else FIN if scenario == "protected_dump_with_finance_key" else ()
    deks = client.unwrap("pii-kek" if fields == PII else "finance-kek",
                         [r["dek_pii_wrapped" if fields == PII else "dek_fin_wrapped"] for r in batch]) if fields else []
    search = {}
    if scenario == "protected_dump_with_search_key":
        for column in SEARCH:
            candidates = [expected[r["legacy_row_id"]][POSITION[column]] for r in batch]
            digests = client.hmac(column, candidates)
            search[column] = {digest: value for digest, value in zip(digests, candidates) if digest is not None}
    result = []
    for i, row in enumerate(batch):
        known = expected[row["legacy_row_id"]]
        exposed = []
        for column in SENSITIVE:
            cfg = profile["columns"][column]
            stored = row[cfg["storage_column"]]
            value = None
            if column in fields:
                value = decrypt(stored, deks[i], column=column, anggota_id=row["anggota_id"], protection_version=row["protection_version"])
                if value != known[POSITION[column]]:
                    raise ValueError("Recovered value differs from known baseline; values withheld")
            elif scenario == "protected_dump_with_search_key" and column in SEARCH:
                value = search[column].get(row[cfg["bidx_column"]])
            elif isinstance(stored, str):
                value = stored
            if known[POSITION[column]] is not None and value == known[POSITION[column]]:
                exposed.append(column)
        result.append(exposed)
    return result


def measure(rows, known, profile, scenario, client=None):
    populations = {g: {"rows": 0, "exposed_cells": Counter(), "direct_exposed_rows": 0} for g in ("all", "source_734", "synthetic")}
    observed_cells = {g: Counter() for g in populations}
    aggregate, seen = AfterAggregation(), set()
    equality = {c: Counter() for c in (*REF, "age_band", *(profile["columns"][c]["bidx_column"] for c in SEARCH))}
    batch, denied = [], {}
    for row in rows:
        identifier = row["legacy_row_id"]
        if identifier in seen or row["protection_version"] != 1:
            raise ValueError("Duplicate or unsupported protected identity")
        seen.add(identifier)
        aggregate.add(row)
        for column, counts in equality.items():
            if row[column] is not None:
                counts[row[column]] += 1
        if not denied and client is not None:
            forbidden = ["finance-kek"] if scenario.endswith("pii_key") else ["pii-kek"] if scenario.endswith("finance_key") else ["pii-kek", "finance-kek"]
            for kek in forbidden:
                wrapped = row["dek_pii_wrapped" if kek == "pii-kek" else "dek_fin_wrapped"]
                denied[kek] = client.denied(kek, wrapped)
                if not denied[kek]:
                    raise ValueError("Attacker policy has excessive decrypt rights")
        batch.append(row)
        if len(batch) == 100:
            account_batch(batch, known, profile, scenario, client, populations, observed_cells)
            batch.clear()
            if len(seen) % 100000 == 0:
                print(json.dumps({"scenario": scenario, "rows_checked": len(seen)}), flush=True)
    if batch:
        account_batch(batch, known, profile, scenario, client, populations, observed_cells)
    for scope in populations:
        if populations[scope]["rows"] != known.meta["population_rows"][scope] or dict(observed_cells[scope]) != known.meta["non_null_cells"][scope]:
            raise ValueError("Incomplete artifact population or NULL coverage")
    histograms = []
    for column, counts in equality.items():
        frequency = Counter(counts.values())
        histograms.append({"column": column, "storage": "blind_index" if column.endswith("_bidx") else "plaintext",
            "equality_classes": len(counts), "largest_class": max(counts.values(), default=0),
            "non_null_cells": sum(counts.values()),
            "frequency_histogram": [{"class_size": n, "number_of_classes": frequency[n]} for n in sorted(frequency)]})
    return populations, aggregate.results(), histograms, denied


def account_batch(batch, known, profile, scenario, client, populations, observed_cells):
    expected = known.lookup([r["legacy_row_id"] for r in batch])
    if len(expected) != len(batch):
        raise ValueError("Unknown protected legacy identity")
    exposed = evaluate_batch(batch, expected, profile, scenario, client)
    for row, columns in zip(batch, exposed):
        values = expected[row["legacy_row_id"]]
        if any(row[c] != values[POSITION[c]] for c in REF) or row["age_band"] != age_band(values[POSITION["tanggal_lahir"]]):
            raise ValueError("Plaintext projection differs from baseline")
        for group in ("all", "source_734" if row["legacy_row_id"] <= 734 else "synthetic"):
            populations[group]["rows"] += 1
            populations[group]["exposed_cells"].update(columns)
            populations[group]["direct_exposed_rows"] += bool(set(columns) & set(DIRECT))
            observed_cells[group].update(c for c in SENSITIVE if row[c + "_ct"] is not None)


def run(artifact, known_path, database, scenario, output=None):
    if database not in {"protected_100k", "protected_1m"} or scenario not in SCENARIOS:
        raise ValueError("Unauthorized protected leakage scope")
    require_disk_space()
    plan = protection_plan(scenario)
    profile = yaml.safe_load((ROOT / "policy/protection_profile.yaml").read_text(encoding="utf-8"))
    artifact, known_path = private_path(artifact), private_path(known_path)
    expanded = artifact.parent / ("expanded_" + database + "_" + scenario + "_" + uuid4().hex + ".sql")
    client = None
    known = KnownValues(known_path)
    started = time.perf_counter()
    try:
        dataset = json.loads((ROOT / "evidence/datasets" / (database.replace("protected_", "baseline_") + ".json")).read_text())
        if known.meta["baseline_checksum_sha256"] != dataset["baseline_checksum_sha256"]:
            raise ValueError("Known-values dataset mismatch")
        # no_key process never constructs a decrypt client or reads a token.
        if scenario != "protected_dump_no_key":
            client = AttackerTransit(scenario)
        expand_dump(artifact, expanded)
        populations, residual, equality, denied = measure(protected_rows(expanded, profile), known, profile, scenario, client)
        output = output or ROOT / "evidence/leakage" / database / (scenario + ".json")
        budget = {"schema_version": 1, "status": "PASSED", "scenario": scenario, "dataset": database,
            "measurement_only": True,
            "timestamp_utc": utc_now(), "artifact_sha256": file_hash(artifact), "artifact_bytes": artifact.stat().st_size,
            "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
            "worktree_code_sha256": {p.relative_to(ROOT).as_posix(): file_hash(p) for p in (ROOT / "verify").glob("*.py")},
            "profile_sha256": file_hash(ROOT / "policy/protection_profile.yaml"),
            "targets_commit": json.loads((ROOT / "evidence/targets_commit.json").read_text())["commit"] if (ROOT / "evidence/targets_commit.json").is_file() else None,
            "profile": plan, "ESCE_scope": "25 contract AEAD columns, excluding REF and operational metadata",
            "method": "Actual COPY artifact; indexed private known-value batch lookup; actual AEAD decrypt or HMAC dictionary oracle",
            "populations": {g: {"rows": values["rows"],
                "ESCE": ratio(sum(values["exposed_cells"].values()), sum(known.meta["non_null_cells"][g].values())),
                "DIE": ratio(values["direct_exposed_rows"], values["rows"]),
                "columns": [{"column": c, **ratio(values["exposed_cells"][c], known.meta["non_null_cells"][g].get(c, 0))} for c in SENSITIVE]}
                for g, values in populations.items()},
            "ELS": {"bidx_count": 3, "plaintext_equality_column_count": 5, "columns": equality},
            "DBR": {"policy": POLICIES.get(scenario), "domains_decrypted": [plan["authorized_decrypt_domain"]] if plan["authorized_decrypt_domain"] else [],
                "forbidden_decrypt_probes": denied,
                "recovered_columns": [c for c in SENSITIVE if populations["all"]["exposed_cells"][c]],
                "crypto_client_constructed": scenario != "protected_dump_no_key"},
            "search_dictionary": {"scope": "All baseline known values for 3 indexed columns; deliberately exhaustive synthetic dictionary upper-bound experiment, not assumed attacker knowledge",
                "active": scenario.endswith("search_key")},
            "elapsed_s": time.perf_counter() - started,
            "target_status": {"S03": ("LULUS" if sum(populations["all"]["exposed_cells"].values()) == 0 else "GAGAL") if scenario == "protected_dump_no_key" else "TIDAK BERLAKU"},
            "limitations": ["Logical dump only, not physical files/WAL", "REF, NULL patterns, legacy locator and equality remain visible",
                "ESCE reports directly recovered exact linked cells; derived/inferred values are not included", "No raw values, dictionary, digests, DEKs or tokens exported"]}
        write_json(output, budget)
        write_json(ROOT / "evidence/leak" / database / (scenario + ".json"), budget)
        if scenario == "protected_dump_no_key":
            residual.update(dataset=database, artifact_sha256=budget["artifact_sha256"], status="PASSED")
            write_json(ROOT / "evidence/leakage" / database / "residual_after.json", residual)
        return budget
    finally:
        known.close()
        if client is not None:
            client.close()
        if expanded.exists():
            expanded.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--known-values", type=Path, required=True)
    parser.add_argument("--db", choices=["protected_100k", "protected_1m"], required=True)
    parser.add_argument("--scenario", choices=SCENARIOS, required=True)
    args = parser.parse_args()
    try:
        result = run(args.artifact, args.known_values, args.db, args.scenario)
        print(json.dumps({"dataset": args.db, "scenario": args.scenario, "status": result["status"], "elapsed_s": result["elapsed_s"]}), flush=True)
    except Exception as error:
        write_json(ROOT / "evidence/leak" / args.db / (args.scenario + "_failure.json"),
                   {"status": "FAILED", "error_type": type(error).__name__, "private_details_withheld": True, "timestamp_utc": utc_now()})
        raise SystemExit("Protected leakage gate failed; private details withheld") from None


if __name__ == "__main__":
    main()
