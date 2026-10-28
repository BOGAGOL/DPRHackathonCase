"""Separate privileged monitoring connection; never expose SQL text or grant workload rights."""

import os

import psycopg
from psycopg.conninfo import conninfo_to_dict


def monitoring_parameters():
    params = conninfo_to_dict(os.environ.get("BENCH_MONITOR_DATABASE_URL", ""))
    if ((params.get("host"), params.get("port")) != ("127.0.0.1", "5433")
            or params.get("user") in {None, "bench_user", "app_user", "scanner_user", "migration_user"}
            or params.get("sslmode") != "verify-full" or not params.get("sslrootcert")):
        raise ValueError("Separate admin/monitoring verify-full connection required")
    params.update(application_name="dpr-benchmark-monitor", options="-c default_transaction_read_only=on", connect_timeout=10)
    return params


def db_time_delta(before, after, requests):
    if requests <= 0 or before["reset"] != after["reset"] or before["dealloc"] != after["dealloc"]:
        raise ValueError("Invalid or reset pg_stat_statements interval")
    calls, milliseconds = 0, 0.0
    for key in before["rows"]:
        if key not in after["rows"]:
            raise ValueError("Statistics entry disappeared")
    for key, (count, elapsed) in after["rows"].items():
        old_count, old_elapsed = before["rows"].get(key, (0, 0.0))
        if count < old_count or elapsed < old_elapsed:
            raise ValueError("Statistics counters decreased")
        calls += count - old_count
        milliseconds += elapsed - old_elapsed
    if calls == 0:
        raise ValueError("No database execution time measured")
    return {"source": "pg_stat_statements", "calls": calls, "requests": requests,
            "total_exec_time_ms": milliseconds, "db_time_ms_per_request": milliseconds / requests,
            "db_time_ms_per_sql_call": milliseconds / calls,
            "scope": "Top-level SQL for the workload role/database only; execution, excluding planning, network and crypto",
            "percentiles": "NOT_AVAILABLE: cumulative execution counters do not provide p50/p95"}


class DbTimeMonitor:
    def __init__(self, database, role):
        if database not in {"baseline_100k", "baseline_1m", "protected_100k", "protected_1m"} or role not in {"bench_user", "app_user"}:
            raise ValueError("Unauthorized monitoring scope")
        self.database, self.role = database, role
        self.connection = psycopg.connect(**monitoring_parameters(), autocommit=True)

    def snapshot(self):
        info = self.connection.execute("SELECT stats_reset,dealloc FROM public.pg_stat_statements_info").fetchone()
        rows = self.connection.execute(
            "SELECT queryid,calls,total_exec_time FROM public.pg_stat_statements "
            "WHERE dbid=(SELECT oid FROM pg_database WHERE datname=%s) "
            "AND userid=(SELECT oid FROM pg_roles WHERE rolname=%s) AND toplevel",
            (self.database, self.role)).fetchall()
        if any(row[0] is None for row in rows):
            raise ValueError("Monitoring identity cannot see query identifiers")
        return {"reset": str(info[0]), "dealloc": info[1], "rows": {str(r[0]): (r[1], r[2]) for r in rows}}

    def close(self):
        self.connection.close()
