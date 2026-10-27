from dataclasses import dataclass

from .models import FIN, SOURCE_FIELDS

ROLES = {"operator", "privileged_officer", "finance_officer", "analyst", "auditor", "anggota"}
RECORD_ROLES = {"operator", "privileged_officer", "finance_officer", "anggota"}
OPERATOR_FIELDS = {"nama", "no_ktp", "email", "handphone", "telpon_jakarta", "telpon_daerah"}
PRIVILEGED_FIELDS = set(SOURCE_FIELDS) - FIN
FINANCE_FIELDS = {"nama", "no_ktp", "rekening", "nama_rekening", "npwp", "kode_bank", "nama_bank", "nama_kppn"}


@dataclass(frozen=True)
class FieldPolicy:
    fields: frozenset[str]
    masked: frozenset[str]


def detail_policy(role):
    if role == "operator":
        return FieldPolicy(frozenset(OPERATOR_FIELDS), frozenset(OPERATOR_FIELDS - {"nama"}))
    if role in {"privileged_officer", "anggota"}:
        return FieldPolicy(frozenset(PRIVILEGED_FIELDS), frozenset())
    if role == "finance_officer":
        return FieldPolicy(frozenset(FINANCE_FIELDS), frozenset({"nama", "no_ktp"}))
    raise PermissionError("Record access denied")


def can_edit(role):
    return role in {"operator", "privileged_officer", "anggota"}


def can_access(role, action):
    if action in {"list", "search", "detail"}:
        return role in RECORD_ROLES
    if action == "update":
        return can_edit(role)
    return role in {"insert": {"privileged_officer"}, "analytics": {"analyst"}, "audit": {"auditor"}}.get(action, set())


def owns_only(role):
    return role == "anggota"


def mask_list_name(role):
    return role in {"operator", "finance_officer"}


def mask(value, column):
    if value is None:
        return None
    if not value or len(value) <= 4:
        return "****"
    if column == "nama":
        return " ".join((word[:2] + "***") for word in value.split())
    if column == "email":
        return value[:1] + "***@***"
    return "********" + value[-2:]
