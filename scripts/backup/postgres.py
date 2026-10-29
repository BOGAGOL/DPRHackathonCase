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
from infra.protected.analyst import security_checks
from .crypto import BackupError


TABLES = ("access_scope", "anggota_protected", "app_users", "audit_log", "migration_jobs")
SERVICE_TABLES = tuple(sorted((*TABLES, "service_member_bindings", "service_sessions")))
RESTORE_NAME = re.compile(r"dpr_restore_[0-9a-f]{32}\Z")


def check_server(connection, *, backup=False):
    version, user, encrypted = connection.execute("SELECT current_setting('server_version_num')::int, current_user, (SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid())").fetchone()
    if not 180000 <= version < 190000 or not encrypted or (backup and user != "backup_user"):
        raise BackupError("postgres18_verified_tls_and_expected_role_required")
    if backup:
        unsafe = connection.execute("SELECT rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb OR rolreplication OR EXISTS(SELECT 1 FROM pg_auth_members WHERE member=r.oid) FROM pg_roles r WHERE rolname=current_user").fetchone()[0]
        if unsafe:
            raise BackupError("unsafe_backup_role")


def validated_tables(names):
    """Accept complete reviewed layouts only, including legacy five-table dumps."""
    try:
        actual = tuple(sorted(names))
    except TypeError:
        raise BackupError("unexpected_public_tables") from None
    if actual not in (TABLES, SERVICE_TABLES):
        raise BackupError("unexpected_public_tables")
    return actual


def row_counts(connection):
    actual = tuple(row[0] for row in connection.execute("SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p') ORDER BY c.relname"))
    return {table: connection.execute(sql.SQL("SELECT count(*) FROM public.{}").format(sql.Identifier(table))).fetchone()[0] for table in validated_tables(actual)}


def check_service_schema(connection):
    """Validate B-owned controls without reading session hashes or account bindings."""
    names = ("service_member_bindings", "service_sessions")
    owners = connection.execute("SELECT relname,pg_get_userbyid(relowner) FROM pg_class WHERE relnamespace='public'::regnamespace AND relname=ANY(%s) ORDER BY relname", (list(names),)).fetchall()
    expected = {
        "service_sessions": {"app_user": {"SELECT", "INSERT", "DELETE"}, "backup_user": {"SELECT"}},
        "service_member_bindings": {"app_user": {"SELECT"}, "admin_user": {"SELECT", "INSERT", "UPDATE", "DELETE"}, "backup_user": {"SELECT"}},
    }
    grants_ok = True
    for table in names:
        for role in ROLES:
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER", "MAINTAIN"):
                actual = connection.execute("SELECT has_table_privilege(%s,%s,%s)", (role, "public."+table, privilege)).fetchone()[0]
                grants_ok &= actual == (privilege in expected[table].get(role, set()))
                if privilege in ("SELECT", "INSERT", "UPDATE", "REFERENCES") and not actual:
                    column_access = connection.execute("SELECT has_any_column_privilege(%s,%s,%s)", (role, "public."+table, privilege)).fetchone()[0]
                    grants_ok &= not column_access
    public_access = connection.execute("SELECT EXISTS(SELECT 1 FROM pg_class c CROSS JOIN LATERAL aclexplode(c.relacl) a WHERE c.relnamespace='public'::regnamespace AND c.relname=ANY(%s) AND a.grantee=0 UNION ALL SELECT 1 FROM pg_attribute t JOIN pg_class c ON c.oid=t.attrelid CROSS JOIN LATERAL aclexplode(t.attacl) a WHERE c.relnamespace='public'::regnamespace AND c.relname=ANY(%s) AND a.grantee=0)", (list(names), list(names))).fetchone()[0]
    sequence = connection.execute("SELECT pg_get_userbyid(c.relowner),s.seqincrement,s.seqcycle FROM pg_sequence s JOIN pg_class c ON c.oid=s.seqrelid WHERE c.oid=to_regclass('public.service_legacy_id_seq')").fetchone()
    sequence_ok = sequence == ("schema_owner", 1, False)
    if sequence_ok:
        last, called = connection.execute("SELECT last_value,is_called FROM public.service_legacy_id_seq").fetchone()
        maximum = connection.execute("SELECT coalesce(max(legacy_row_id),0) FROM public.anggota_protected").fetchone()[0]
        sequence_ok = maximum < last + int(called) <= 9223372036854775807
    sequence_grants = bool(sequence)
    if sequence:
        for role in ROLES:
            for privilege in ("USAGE", "SELECT", "UPDATE"):
                actual = connection.execute("SELECT has_sequence_privilege(%s,'public.service_legacy_id_seq',%s)", (role, privilege)).fetchone()[0]
                sequence_grants &= actual == ((role, privilege) in {("app_user", "USAGE"), ("backup_user", "SELECT")})
        sequence_public = connection.execute("SELECT EXISTS(SELECT 1 FROM pg_class c CROSS JOIN LATERAL aclexplode(c.relacl) a WHERE c.oid='public.service_legacy_id_seq'::regclass AND a.grantee=0)").fetchone()[0]
        sequence_grants &= not sequence_public
    checks = {
        "service_tables_owned_by_schema_owner": owners == [(name, "schema_owner") for name in names],
        "service_table_grants_minimal": bool(grants_ok) and not public_access,
        "service_locator_sequence_safe": bool(sequence_ok),
        "service_locator_sequence_grants": bool(sequence_grants),
    }
    if not all(checks.values()):
        raise BackupError("service_schema_validation_failed")
    return checks


def check_roles(connection):
    rows = connection.execute("SELECT rolname,rolsuper,rolbypassrls,rolcreaterole,rolcreatedb,rolreplication,rolcanlogin,EXISTS(SELECT 1 FROM pg_auth_members WHERE member=r.oid) FROM pg_roles r WHERE rolname=ANY(%s)", (["schema_owner", *ROLES],)).fetchall()
    if len(rows) != 8 or any(any(row[1:6]) or row[7] or (row[0] == "schema_owner" and row[6]) for row in rows):
        raise BackupError("restore_requires_preprovisioned_safe_contract_roles")


def check_restored_security(connection, *, service=False):
    check_roles(connection)
    table = connection.execute("SELECT pg_get_userbyid(relowner),relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid='public.anggota_protected'::regclass").fetchone()
    checks = {
        "schema_owner_and_forced_rls": table == ("schema_owner", True, True),
        "app_has_no_ddl": not connection.execute("SELECT has_schema_privilege('app_user','public','CREATE')").fetchone()[0],
        "analyst_cannot_select_base": not connection.execute("SELECT has_table_privilege('analyst_user','public.anggota_protected','SELECT')").fetchone()[0],
        "backup_can_select_base": connection.execute("SELECT has_table_privilege('backup_user','public.anggota_protected','SELECT')").fetchone()[0],
        "app_principal_rls_present": connection.execute("SELECT EXISTS(SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='anggota_protected' AND (qual LIKE %s OR with_check LIKE %s)) AND pg_get_functiondef('public.request_principal()'::regprocedure) LIKE %s", ('%request_principal%', '%request_principal%', '%app.principal%')).fetchone()[0],
        "public_database_connect_revoked": not connection.execute("SELECT EXISTS(SELECT 1 FROM pg_database d, LATERAL aclexplode(coalesce(d.datacl,acldefault('d',d.datdba))) a WHERE d.datname=current_database() AND a.grantee=0 AND a.privilege_type='CONNECT')").fetchone()[0],
    }
    checks.update(security_checks(connection))
    if not all(checks.values()):
        raise BackupError("restored_security_validation_failed")
    if service:
        checks.update(check_service_schema(connection))
    return checks


class Tools:
    """Only a public CA certificate is copied; credentials travel in environment."""

    def __init__(self, container, parameters):
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", container):
            raise BackupError("invalid_container_name")
        self.container = container
        self.parameters = parameters
        self.native_bin = os.environ.get("DPR_BACKUP_NATIVE_PG_BIN")
        if self.native_bin is not None:
            self.native_bin = Path(self.native_bin)
            if not self.native_bin.is_absolute() or not self.native_bin.is_dir():
                raise BackupError("invalid_native_pg_directory")
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
        if self.native_bin is not None:
            self.environment.update(PGHOST=self.parameters["host"], PGPORT=str(self.parameters["port"]),
                                    PGSSLROOTCERT=self.parameters["sslrootcert"])
            return self
        result = subprocess.run(["docker", "cp", str(Path(self.parameters["sslrootcert"]).resolve()), self.container+":"+self.ca],
            env=self.environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        if result.returncode:
            raise BackupError("public_ca_copy_failed")
        return self

    def __exit__(self, *_):
        if self.native_bin is not None:
            return
        subprocess.run(["docker", "exec", self.container, "rm", "-f", "--", self.ca],
            env=self.environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)

    def command(self, program, arguments):
        if program not in {"pg_dump", "pg_restore", "psql"}:
            raise BackupError("invalid_pg_program")
        if self.native_bin is not None:
            executable = self.native_bin / (program + (".exe" if os.name == "nt" else ""))
            if not executable.is_file():
                raise BackupError("native_pg_program_missing")
            return [str(executable), "--no-password", *arguments]
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


def allow_runtime_connections(parameters, created, *, service=False):
    # Publish CONNECT only after all authentication/validation has succeeded.
    marker = created["marker"]
    if service:
        marker = "dpr-service-restore-v1:" + marker.removeprefix("dpr-backup-v1:")
    with psycopg.connect(**parameters) as admin:
        actual = admin.execute("SELECT oid,shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()").fetchone()
        if actual != (created["oid"], created["marker"]):
            raise BackupError("restore_database_identity_changed")
        admin.execute(sql.SQL("COMMENT ON DATABASE {} IS {}").format(sql.Identifier(parameters["dbname"]), sql.Literal(marker)))
        admin.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(parameters["dbname"]), sql.SQL(",").join(map(sql.Identifier, ROLES))))
    return {**created, "marker": marker}


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
