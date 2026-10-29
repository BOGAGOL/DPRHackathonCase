"""Bounded correctness gate, not a duration/concurrency performance benchmark."""

import argparse
import copy
import json
import os
from pathlib import Path
import random
import secrets
from uuid import uuid4

from argon2 import PasswordHasher
import psycopg
import yaml

from .adapters.plaintext import PlaintextAdapter, load_keys
from .adapters.protected import ProtectedAdapter, READS, cache_configuration
from .common import ROOT, parameters, utc_now, write_json, file_hash
from .db_time import DbTimeMonitor, db_time_delta, monitoring_parameters


def parity_keys(keys, connection, rows, samples=1000):
    if samples > len(keys["profiles"]) or samples > rows // 50:
        raise ValueError("Insufficient distinct parity keys")
    result = copy.deepcopy(keys)
    rng = random.Random(42)
    result["profiles"] = rng.sample(keys["profiles"], samples)
    result["pages"] = []
    for anchor in rng.sample(range(0, rows - 49, 50), samples):
        page = connection.execute("SELECT id,nama,jenis_kelamin FROM public.anggota WHERE id>%s ORDER BY id LIMIT %s",
                                  (anchor, 50)).fetchall()
        result["pages"].append({"anchor": anchor, "rows": [list(r) for r in page]})
    return result


def prepare_scope(connection, keys):
    """Admin-only temporary benchmark principal; no role grants or row changes."""
    principal = str(uuid4())
    identifiers = sorted({r["id"] for r in keys["profiles"]} |
                         {r[0] for page in keys["pages"] for r in page["rows"]})
    password_hash = PasswordHasher().hash(secrets.token_urlsafe(48))
    with connection.transaction():
        connection.execute("INSERT INTO public.app_users(user_id,username,password_hash,role) VALUES (%s,%s,%s,%s)",
                           (principal, "benchmark-parity-" + principal, password_hash, "privileged_officer"))
        # update permission includes read under the schema's existing RLS policy.
        connection.execute("INSERT INTO public.access_scope(principal,anggota_id,permission,source_label) "
                           "SELECT %s,anggota_id,'update','synthetic' FROM public.anggota_protected WHERE legacy_row_id=ANY(%s)",
                           (principal, identifiers))
        actual = connection.execute("SELECT count(*) FROM public.access_scope WHERE principal=%s", (principal,)).fetchone()[0]
        if actual != len(identifiers):
            raise ValueError("Parity scope coverage incomplete")
        connection.execute("INSERT INTO public.access_scope(principal,permission,source_label) VALUES (%s,'insert','synthetic')", (principal,))
    return principal, len(identifiers)


def remove_scope(connection, principal):
    with connection.transaction():
        connection.execute("DELETE FROM public.app_users WHERE user_id=%s", (principal,))
        remaining = connection.execute("SELECT count(*) FROM public.access_scope WHERE principal=%s", (principal,)).fetchone()[0]
        if remaining:
            raise ValueError("Temporary scope cleanup incomplete")


def check_dataset(baseline, protected, rows, samples=1000):
    manifest = yaml.safe_load((ROOT / "benchmark/workloads.yaml").read_text())
    corpus, identity = load_keys(manifest, 8, baseline)
    principal, protected_session, monitor = None, None, None
    previous_principal = os.environ.get("DPR_BENCH_PRINCIPAL")
    admin_params = monitoring_parameters()
    admin_params.update(dbname=protected, options="-c statement_timeout=120000")
    with psycopg.connect(**parameters(baseline), autocommit=True) as plain_connection, psycopg.connect(**admin_params, autocommit=True) as admin:
        keys = parity_keys(corpus, plain_connection, rows, samples)
        principal, authorized = prepare_scope(admin, keys)
        try:
            os.environ["DPR_BENCH_PRINCIPAL"] = principal
            plain = PlaintextAdapter(keys, baseline)
            adapter = ProtectedAdapter(keys, protected)
            protected_session = adapter.connect()
            monitor = DbTimeMonitor(protected, "app_user")
            report = {"baseline": baseline, "protected": protected, "samples_per_read": samples,
                      "baseline_key_corpus": identity, "authorized_record_count": authorized, "scenarios": {}}
            for scenario in READS:
                before = monitor.snapshot()
                mismatches = 0
                for index in range(samples):
                    expected = plain.execute(plain_connection, scenario, index, 0)
                    actual = adapter.execute(protected_session, scenario, index, 0)
                    mismatches += actual != expected
                    if mismatches:
                        raise ValueError("Adapter parity mismatch (values withheld)")
                report["scenarios"][scenario] = {"passed": True, "requests": samples,
                    "distinct_lookup_keys": samples, "mismatches": mismatches,
                    "business_rows_compared": samples * (50 if scenario == "list_page" else 1),
                    "db_time": db_time_delta(before, monitor.snapshot(), samples)}
            # One correctness probe per write, rolled back by both adapters.
            for scenario in ("update_contact", "insert_member"):
                plain.execute(plain_connection, scenario, 0, 0)
                adapter.execute(protected_session, scenario, 0, 0)
            if plain.execute(plain_connection, "read_profile", 0, 0) != adapter.execute(protected_session, "read_profile", 0, 0):
                raise ValueError("Business profile differs after rollback probes")
            report["write_rollback_probes"] = {"update_contact": "PASS", "insert_member": "PASS"}
            report["passed"] = True
            return report
        finally:
            if protected_session is not None:
                protected_session.close()
            if monitor is not None:
                monitor.close()
            remove_scope(admin, principal)
            if previous_principal is None:
                os.environ.pop("DPR_BENCH_PRINCIPAL", None)
            else:
                os.environ["DPR_BENCH_PRINCIPAL"] = previous_principal


def run(output=ROOT / "evidence/benchmark/adapter_parity.json", samples=1000):
    ttl, entries = cache_configuration()
    report = {"schema_version": 2, "gate": 3, "passed": False, "started_at_utc": utc_now(),
              "measurement_kind": "correctness_only", "official_benchmark_executed": False,
              "samples_required_per_read_scenario_per_dataset": samples, "datasets": [],
              "dek_cache_ttl_seconds": ttl, "dek_cache_max_entries_per_worker": entries,
              "http_transport": os.environ.get('DPR_OPENBAO_HTTP_TRANSPORT', 'https_pool'),
              "production_files_sha256": {p: file_hash(ROOT / p) for p in (
                  'benchmark/adapters/protected.py', 'toolkit/dprcrypto/openbao.py',
                  'toolkit/dprcrypto/keys.py', 'toolkit/dprcrypto/bidx.py',
                  'toolkit/dprcrypto/https_pool.py')},
              "workload_role": "app_user", "rls_bypassed": False,
              "monitoring": "separate admin connection; no workload role grants", "values_withheld": True}
    try:
        for size, rows in (("100k", 100000), ("1m", 1000000)):
            report["datasets"].append(check_dataset("baseline_" + size, "protected_" + size, rows, samples))
            write_json(output, report)
        report.update(passed=True, status="PASSED")
    except Exception as error:
        report.update(status="FAILED", error_type=type(error).__name__, error="parity_gate_failed_private_details_withheld")
    finally:
        report["completed_at_utc"] = utc_now()
        write_json(output, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "evidence/benchmark/adapter_parity.json")
    args = parser.parse_args()
    result = run(args.out)
    print("Protected adapter parity: " + ("PASS" if result["passed"] else "FAIL") + "; values withheld")
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
