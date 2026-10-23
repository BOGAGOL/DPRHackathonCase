"""Policy can be exercised without HTTP or cryptography."""
from sqlalchemy import select

from .models import Assignment, Member, User

CONTACT = {"email", "handphone", "telpon_jakarta", "telpon_daerah"}
ADDRESS = {"alamat_jakarta", "alamat_daerah"}
FINANCE = {"rekening", "nama_rekening", "npwp", "nama_bank"}
ROLES = {"public", "operator", "staff", "admin"}
PERMISSIONS = {"search:ktp", "read:identity", "read:contact", "read:address", "read:finance",
               "write:contact", "write:address", "audit:read", "users:manage"}


def has(user: User, permission: str) -> bool:
    # Administrative identity grants no automatic data access.
    if permission in {"audit:read", "users:manage"}:
        return user.role == "admin" and permission in user.permissions
    if user.role not in {"operator", "staff"}:
        return False
    if permission.startswith("read:") and user.role != "staff":
        return False
    return permission in user.permissions


def member_scope(user: User):
    if user.role == "public":
        return True
    return Member.id.in_(select(Assignment.member_id).where(Assignment.user_id == user.id))


def readable_fields(user: User) -> set[str]:
    result = set()
    for permission, fields in [("read:contact", CONTACT), ("read:address", ADDRESS),
                                ("read:finance", FINANCE), ("read:identity", {"no_ktp", "tanggal_lahir"})]:
        if has(user, permission):
            result.update(fields)
    return result


def editable_fields(user: User) -> set[str]:
    return (CONTACT if has(user, "write:contact") else set()) | (ADDRESS if has(user, "write:address") else set())


def masked(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    # Never reveal short values in full; email domains are also withheld.
    if len(value) <= 4:
        return "••••"
    if field == "email":
        return value[:1] + "••••@••••"
    return "••••••" + value[-2:]
