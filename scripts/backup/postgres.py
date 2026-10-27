"""PG18 tools in the existing container, verified TLS and pipe-only dump bytes."""

from contextlib import contextmanager
import os
from pathlib import Path
import re
import subprocess
from uuid import uuid4

import psycopg
from psycopg import sql

from infra.protected.credentials import ROLES
from .crypto import BackupError


TABLES = ("access_scope", "anggota_protected", "app_users", "audit_log", "migration_jobs")
RESTORE_NAME = re.compile(r"dpr_restore_[0-9a-f]{32}\Z")


def check_server(connection, *, backup=False):
    version, user, encrypted = connection.execute("SELECT current_setting('server_version_num')::int, current_user, (SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid())").fetchone()
    if not 180000 <= version < 190000 or not encrypted or (backup and user != "backup_user"):
        raise BackupError("postgres18_verified_tls_and_expected_role_required")
    if backup:
        unsafe = connection.execute("SELECT rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb OR rolreplication OR EXISTS(SELECT 1 FROM pg_auth_members WHERE member=r.oid) FROM pg_roles r WHERE rolname=current_user").fetchone()[0]
        if unsafe:
            raise BackupError("unsafe_backup_role")


def row_counts(connection):
    actual = tuple(row[0] for row in connection.execute("SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p') ORDER BY c.relname"))
    if actual != TABLES:
        raise BackupError("unexpected_public_tables")
    return {table: connection.execute(sql.SQL("SELECT count(*) FROM public.{}").format(sql.Identifier(table))).fetchone()[0] for table in TABLES}


def check_roles(connection):
    rows = connection.execute("SELECT rolname,rolsuper,rolbypassrls,rolcreaterole,rolcreatedb,rolreplication,rolcanlogin,EXISTS(SELECT 1 FROM pg_auth_members WHERE member=r.oid) FROM pg_roles r WHERE rolname=ANY(%s)", (["schema_owner", *ROLES],)).fetchall()
    if len(rows) != 8 or any(any(row[1:6]) or row[7] or (row[0] == "schema_owner" and row[6]) for row in rows):
        raise BackupError("restore_requires_preprovisioned_safe_contract_roles")


def check_restored_security(connection):
    check_roles(connection)
    table = connection.execute("SELECT pg_get_userbyid(relowner),relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid='public.anggota_protected'::regclass").fetchone()
    checks = {
        "schema_owner_and_forced_rls": table == ("schema_owner", True, True),
        "app_has_no_ddl": not connection.execute("SELECT has_schema_privilege('app_user','public','CREATE')").fetchone()[0],
        "analyst_cannot_select_base": not connection.execute("SELECT has_table_privilege('analyst_user','public.anggota_protected','SELECT')").fetchone()[0],
        "analyst_can_select_view": connection.execute("SELECT has_table_privilege('analyst_user','public.analyst_view','SELECT')").fetchone()[0],
        "backup_can_select_base": connection.execute("SELECT has_table_privilege('backup_user','public.anggota_protected','SELECT')").fetchone()[0],
        "app_principal_rls_present": connection.execute("SELECT EXISTS(SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='anggota_protected' AND (qual LIKE %s OR with_check LIKE %s)) AND pg_get_functiondef('public.request_principal()'::regprocedure) LIKE %s", ('%request_principal%', '%request_principal%', '%app.principal%')).fetchone()[0],
        "public_database_connect_revoked": not connection.execute("SELECT EXISTS(SELECT 1 FROM pg_database d, LATERAL aclexplode(coalesce(d.datacl,acldefault('d',d.datdba))) a WHERE d.datname=current_database() AND a.grantee=0 AND a.privilege_type='CONNECT')").fetchone()[0],
    }
    if not all(checks.values()):
        raise BackupError("restored_security_validation_failed")
    return checks


class Tools:
    """Only a public CA certificate is copied; credentials travel in environment."""

    def __init__(self, container, parameters):
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", container):
            raise BackupError("invalid_container_name")
        self.container = container
        self.parameters = parameters
        self.ca = "/tmp/dpr-backup-ca-" + uuid4().hex + ".crt"
        allowed = {"PATH", "SystemRoot", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "USERPROFILE", "HOME",
                   "APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "HOMEDRIVE", "HOMEPATH", "DOCKER_HOST",
                   "DOCKER_CONTEXT", "DOCKER_CONFIG", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"}
        self.environment = {key: value for key, value in os.environ.items() if key in allowed}
        self.environment.update(PGUSER=parameters["user"], PGPASSWORD=parameters["password"],
            PGDATABASE=parameters["dbname"], PGHOST="127.0.0.1", PGPORT="5432", PGSSLMODE="verify-full",
            PGSSLROOTCERT=self.ca, PGGSSENCMODE="disable", PGCONNECT_TIMEOUT="10",
            PGAPPNAME=parameters.get("application_name", "dpr-backup-"+uuid4().hex))

    def __enter__(self):
        result = subprocess.run(["docker", "cp", str(Path(self.parameters["sslrootcert"]).resolve()), self.container+":"+self.ca],
            env=self.environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        if result.returncode:
            raise BackupError("public_ca_copy_failed")
        return self

    def __exit__(self, *_):
        subprocess.run(["docker", "exec", self.container, "rm", "-f", "--", self.ca],
            env=self.environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)

    def command(self, program, arguments):
        if program not in {"pg_dump", "pg_restore", "psql"}:
            raise BackupError("invalid_pg_program")
        command = ["docker", "exec", "-i"]
        for name in self.environment:
            if name.startswith("PG"):
                command.extend(["--env", name])
        return command + [self.container, program, "--no-password", *arguments]

    def bind(self):
        # The caller keeps its random application_name session open. Same role can
        # inspect its own sessions without granting pg_read_all_stats.
        probe = b"SELECT count(*) FROM pg_stat_activity WHERE application_name=current_setting('application_name') AND usename=current_user AND datname=current_database() AND pid<>pg_backend_pid();"
        result = subprocess.run(self.command("psql", ["-X", "-A", "-t", "-v", "ON_ERROR_STOP=1"]),
            input=probe, env=self.environment, capture_output=True, timeout=30)
        if result.returncode or result.stdout.strip() != b"1":
            raise BackupError("container_and_tls_connection_do_not_match")

    @contextmanager
    def process(self, program, arguments):
        child = subprocess.Popen(self.command(program, arguments), env=self.environment,
            stdin=subprocess.PIPE if program == "pg_restore" else subprocess.DEVNULL,
            stdout=subprocess.PIPE if program == "pg_dump" else subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            yield child
            if child.stdin:
                child.stdin.close()
            if child.wait(timeout=300):
                raise BackupError(program + "_failed_output_withheld")
        finally:
            if child.poll() is None:
                child.terminate()
                try: child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill(); child.wait(timeout=10)
            if child.stdout: child.stdout.close()
            if child.stdin and not child.stdin.closed: child.stdin.close()


def create_database(admin_parameters, artifact_id, name=None):
    name = name or "dpr_restore_"+uuid4().hex
    if not RESTORE_NAME.fullmatch(name):
        raise BackupError("restore_requires_reserved_new_database_name")
    with psycopg.connect(**{**admin_parameters, "dbname": "postgres"}, autocommit=True) as admin:
        check_server(admin); check_roles(admin)
        # CREATE DATABASE itself atomically refuses an existing name; no overwrite.
        admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(name)))
        oid = admin.execute("SELECT oid FROM pg_database WHERE datname=%s", (name,)).fetchone()[0]
        marker = "dpr-backup-v1:"+artifact_id
        try:
            admin.execute(sql.SQL("COMMENT ON DATABASE {} IS {}").format(sql.Identifier(name), sql.Literal(marker)))
            admin.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(name)))
        except BaseException:
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
            raise
    return {"name": name, "oid": oid, "marker": marker}


def allow_runtime_connections(parameters):
    # Publish CONNECT only after all authentication/validation has succeeded.
    with psycopg.connect(**parameters) as admin:
        admin.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(parameters["dbname"]), sql.SQL(",").join(map(sql.Identifier, ROLES))))


def drop_created_database(admin_parameters, created):
    if not RESTORE_NAME.fullmatch(created["name"]):
        raise BackupError("unsafe_cleanup_database_name")
    with psycopg.connect(**{**admin_parameters, "dbname": "postgres"}, autocommit=True) as admin:
        actual = admin.execute("SELECT oid,shobj_description(oid,'pg_database') FROM pg_database WHERE datname=%s", (created["name"],)).fetchone()
        if actual is None:
            return
        if actual != (created["oid"], created["marker"]):
            raise BackupError("cleanup_database_identity_changed")
        admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(created["name"])))
