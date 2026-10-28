"""Bounded CAS batches and isolated operator/validator subprocesses.

No minimum-decryption/encryption version is changed; old backups stay readable.
"""

from contextlib import ExitStack
from datetime import datetime, timezone
import json
import os
import subprocess
import sys
import time

import psycopg
from psycopg.types.json import Jsonb

from infra.security import REPO
from infra.targets import PROTECTED_DATABASES
from .worker import RotationError


LOCK = 734100019


def worker_environment(kind, reader=None):
    if kind not in {"operator", "validator"}: raise RotationError("invalid_worker")
    names = {"PATH", "SystemRoot", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP"}
    result = {name: value for name, value in os.environ.items() if name in names}
    result.update(PYTHONIOENCODING="utf-8", OPENBAO_ADDR=os.environ["OPENBAO_ADDR"],
        OPENBAO_CACERT=os.environ["OPENBAO_CACERT"])
    token = "OPENBAO_KEY_OPERATOR_TOKEN" if kind == "operator" else "OPENBAO_VALIDATION_TOKEN"
    result[token] = os.environ[token]
    if kind == "validator":
        result.update(PGHOST=reader["host"], PGPORT=str(reader["port"]), PGUSER=reader["user"],
            PGPASSWORD=reader["password"], PGSSLROOTCERT=reader["sslrootcert"])
    return result


class Worker:
    def __init__(self, kind, reader=None):
        self.kind = kind; self.reader = reader; self.child = None

    def __enter__(self):
        self.child = subprocess.Popen([sys.executable, "-m", "infra.rotation.worker", self.kind], cwd=REPO,
            env=worker_environment(self.kind, self.reader), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1)
        return self

    def request(self, message):
        try:
            self.child.stdin.write(json.dumps(message)+"\n"); self.child.stdin.flush()
            while True:
                line = self.child.stdout.readline()
                if not line: raise RotationError("worker_unavailable")
                result = json.loads(line)
                if "progress_rows" in result:
                    if type(result["progress_rows"]) is not int: raise RotationError("invalid_worker_response")
                    print(json.dumps({"phase": message["action"], "database": message.get("database"), "validated_rows": result["progress_rows"]}), flush=True)
                    continue
                if result.get("ok") is not True: raise RotationError("worker_operation_failed")
                return result["result"]
        except (OSError, ValueError, KeyError):
            raise RotationError("worker_protocol_failed") from None

    def __exit__(self, *_):
        if not self.child: return
        try:
            self.child.stdin.close()
            self.child.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            self.child.kill(); self.child.wait(timeout=10)
        finally:
            self.child.stdout.close()


def prepare(parameters):
    if parameters["dbname"] not in PROTECTED_DATABASES:
        raise RotationError("invalid_database")
    with psycopg.connect(**parameters) as connection:
        database, version, tls = connection.execute("SELECT current_database(),current_setting('server_version_num')::int,(SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid())").fetchone()
        if database != parameters["dbname"] or version//10000 != 18 or not tls:
            raise RotationError("invalid_database_or_tls")
        connection.execute("SET LOCAL lock_timeout='5s'")
        connection.execute((REPO/"sql/protected/03_rotation.sql").read_text(encoding="utf-8"), prepare=False)
    return {"passed": True, "database": parameters["dbname"], "new_tables": 0,
            "admin_access": "wrapped PII DEK maintenance functions only"}


def status(connection):
    return {str(version): count for version, count in connection.execute("SELECT * FROM public.pii_rotation_status()")}


def check_database(connection, database):
    identity = connection.execute("SELECT current_database(),current_setting('server_version_num')::int,current_user,(SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid())").fetchone()
    if database not in PROTECTED_DATABASES or identity[0] != database or identity[1]//10000 != 18 or identity[2:] != ("admin_user", True):
        raise RotationError("invalid_rotation_database_role_or_tls")
    role = connection.execute("SELECT rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole OR rolreplication OR EXISTS(SELECT 1 FROM pg_auth_members WHERE member=r.oid) FROM pg_roles r WHERE rolname=current_user").fetchone()[0]
    if role or connection.execute("SELECT has_table_privilege(current_user,'public.anggota_protected','UPDATE') OR has_table_privilege(current_user,'public.anggota_protected','SELECT')").fetchone()[0]:
        raise RotationError("rotation_coordinator_must_have_only_function_access")
    if not connection.execute("SELECT pg_try_advisory_lock(%s)", (LOCK,)).fetchone()[0]:
        raise RotationError("rotation_already_running")
    status(connection)  # Fail before rotating if prepare/functions/grants missing.


def execute(databases, writer, reader, *, batch_size=100, resume_version=None, max_batches=None,
            checkpoint=None, worker_factory=Worker):
    if (not databases or len(set(databases)) != len(databases) or any(db not in PROTECTED_DATABASES for db in databases)
            or type(batch_size) is not int or not 1 <= batch_size <= 100
            or (resume_version is not None and (type(resume_version) is not int or resume_version < 1))
            or (max_batches is not None and (type(max_batches) is not int or max_batches < 1))):
        raise RotationError("invalid_rotation_arguments")
    started = time.perf_counter()
    report = {"schema_version": 1, "passed": False, "status": "preflight", "key": "pii-kek",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(), "databases": {}, "completed_batches": 0,
        "key_operator_has_database_credentials": False, "plaintext_or_deks_written": False,
        "minimum_key_versions_changed": False, "validation": "all records, all PII/FIN fields, private in-memory comparisons"}
    report["resumed"] = resume_version is not None
    def save():
        report["elapsed_seconds"] = round(time.perf_counter()-started, 6)
        if checkpoint: checkpoint(report)
    try:
        with ExitStack() as stack:
            connections = {}
            for database in sorted(databases):
                connection = stack.enter_context(psycopg.connect(**{**writer, "dbname": database}, autocommit=True))
                connections[database] = connection; check_database(connection, database)
                report["databases"][database] = {"before_versions": status(connection), "rewrapped_rows": 0}
            operator = stack.enter_context(worker_factory("operator"))
            validator = stack.enter_context(worker_factory("validator", reader))
            metadata = operator.request({"action": "metadata"})
            report["key_version_before"] = metadata["latest_version"]
            report["min_decryption_version_before"] = metadata["min_decryption_version"]
            for database in databases:
                details = report["databases"][database]
                if any(int(version) > metadata["latest_version"] for version in details["before_versions"]):
                    raise RotationError("stored_key_version_newer_than_openbao")
                print(json.dumps({"phase": "validate_before", "database": database}), flush=True)
                details["before_validation"] = validator.request({"action": "before", "database": database})
                if details["before_validation"]["rows"] != sum(details["before_versions"].values()):
                    raise RotationError("concurrent_data_change")
            if resume_version is None:
                report["status"] = "rotate_requested"; save()
                metadata = operator.request({"action": "rotate"})
                if metadata["latest_version"] != report["key_version_before"]+1:
                    raise RotationError("concurrent_key_rotation")
                target = metadata["latest_version"]
            else:
                target = resume_version
                if not metadata["min_encryption_version"] <= target <= metadata["latest_version"]:
                    raise RotationError("invalid_resume_version")
            report.update(target_version=target, status="rewrapping"); save()
            paused = False
            for database in databases:
                connection = connections[database]; details = report["databases"][database]; after = None
                while True:
                    page = connection.execute("SELECT * FROM public.pii_rotation_page(%s,%s,%s)", (after, batch_size, target)).fetchall()
                    if not page: break
                    if max_batches is not None and report["completed_batches"] >= max_batches:
                        paused = True; break
                    replacements = operator.request({"action": "rewrap", "wrapped": [row[2] for row in page], "version": target})
                    if len(replacements) != len(page): raise RotationError("invalid_rewrap_batch")
                    changes = [{"anggota_id": str(row[1]), "old_wrapped": row[2], "new_wrapped": wrapped} for row, wrapped in zip(page, replacements)]
                    with connection.transaction():
                        changed = connection.execute("SELECT public.pii_rotation_apply(%s,%s)", (Jsonb(changes), target)).fetchone()[0]
                        if changed != len(page): raise RotationError("incomplete_batch")
                    details["rewrapped_rows"] += changed; after = page[-1][0]
                    report["completed_batches"] += 1; save()
                details["after_versions"] = status(connection)
                print(json.dumps({"phase": "validate_after", "database": database}), flush=True)
                details["validation"] = validator.request({"action": "after", "database": database})
                details["all_rows_at_target_or_newer"] = all(int(version) >= target for version in details["after_versions"])
                if not paused and not details["all_rows_at_target_or_newer"]:
                    raise RotationError("rows_not_fully_rewrapped")
            final_metadata = operator.request({"action": "metadata"})
            if final_metadata["min_decryption_version"] != report["min_decryption_version_before"]:
                raise RotationError("concurrent_minimum_key_version_change")
            report.update(passed=not paused, status="paused" if paused else "complete", key_version_after=final_metadata["latest_version"])
    except BaseException:
        report["status"] = "failed"; save()
        raise
    save()
    return report
