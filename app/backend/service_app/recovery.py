"""Read-only startup gate for the exact restored target selected by its operator."""
import re
from uuid import UUID

from sqlalchemy import text


def verify_restore_target(connection, expected_database):
    connection.execute(text("SET TRANSACTION READ ONLY"))
    state = connection.execute(text("SELECT current_database(),current_user,(SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()),shobj_description(d.oid,'pg_database'),r.rolsuper OR r.rolbypassrls OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication OR EXISTS(SELECT 1 FROM pg_auth_members WHERE member=r.oid),has_schema_privilege(current_user,'public','CREATE') FROM pg_database d JOIN pg_roles r ON r.rolname=current_user WHERE d.datname=current_database()")).one()
    marker = state[3]
    try:
        if not isinstance(marker, str) or not marker.startswith("dpr-service-restore-v1:"):
            raise ValueError()
        identity = marker.removeprefix("dpr-service-restore-v1:")
        if str(UUID(identity)) != identity:
            raise ValueError()
        if (not re.fullmatch(r"dpr_restore_[0-9a-f]{32}", expected_database)
                or tuple(state[:3]) != (expected_database, "app_user", True) or state[4] or state[5]):
            raise ValueError()
        tables = connection.execute(text("SELECT relname FROM pg_class WHERE relnamespace='public'::regnamespace AND relkind IN ('r','p') ORDER BY relname")).scalars().all()
        if tables != ["access_scope", "anggota_protected", "app_users", "audit_log", "migration_jobs", "service_member_bindings", "service_sessions"]:
            raise ValueError()
        protected = connection.execute(text("SELECT pg_get_userbyid(relowner),relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid='public.anggota_protected'::regclass")).one()
        if tuple(protected) != ("schema_owner", True, True):
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Verified service restore target required") from None
