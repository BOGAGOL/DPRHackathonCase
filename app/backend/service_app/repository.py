"""Equal business operations with minimum projections and server-side object scope."""
from datetime import date
import uuid

from sqlalchemy import func, select, text, update

from .crypto import CryptoUnavailable, checked_result
from .models import FIN, PII, REF, SOURCE_FIELDS, baseline_members, protected_members, utcnow
from .policy import owns_only
from .protected_control import scopes

PLAIN_TABLE, PROTECTED_TABLE = baseline_members, protected_members


class DuplicateIdentity(Exception):
    """The plain API write invariant; never carry identity values in this error."""


def identity_conflict(error):
    """Recognize only F-01's index, not unrelated integrity/database failures."""
    original = error.orig
    if getattr(original, "sqlstate", None) == "23505":
        return getattr(getattr(original, "diag", None), "constraint_name", None) == "uq_anggota_protected_no_ktp_bidx"
    return (getattr(original, "sqlite_errorname", None) == "SQLITE_CONSTRAINT_UNIQUE"
            and str(original) == "UNIQUE constraint failed: anggota_protected.no_ktp_bidx")


def normalized(column, value):
    if column == "no_ktp":
        return "".join(c for c in value if c in "0123456789")
    return value.strip().lower() if column == "email" else value.strip()


def text_value(value):
    if value is None:
        return None
    return value.isoformat() if isinstance(value, date) else str(value)


class MemberRepository:
    def __init__(self, mode, crypto, testing=False):
        self.mode, self.crypto = mode, crypto
        self.testing = testing
        self.table = PLAIN_TABLE if mode == "plain" else PROTECTED_TABLE
        self.identifier = self.table.c.id if mode == "plain" else self.table.c.legacy_row_id

    def scope(self, user, permission="read"):
        if self.mode == "plain":
            return self.table.c.pengguna == user.principal if owns_only(user.role) else True
        permitted = scopes.c.permission.in_(["read", "update"]) if permission == "read" else scopes.c.permission == permission
        assigned = select(scopes.c.scope_id).where(scopes.c.principal == user.id,
            scopes.c.anggota_id == self.table.c.anggota_id, permitted).exists()
        if not owns_only(user.role):
            return assigned
        if user.principal.startswith("bidx:v1:"):
            try:
                index = bytes.fromhex(user.principal[8:])
                if len(index) != 32:
                    raise ValueError()
            except ValueError:
                raise CryptoUnavailable("Invalid member binding") from None
            return assigned & (self.table.c.pengguna_bidx == index)
        raise CryptoUnavailable("Protected member binding must use a blind index")

    def _crypto(self, method, *args, **kwargs):
        try:
            return checked_result(method, getattr(self.crypto, method)(*args, **kwargs), args)
        except Exception:
            raise CryptoUnavailable("Protected operation failed") from None

    def projection(self, fields):
        if self.mode == "plain":
            return [self.identifier, *(self.table.c[f] for f in sorted(fields))]
        domains = {"pii" for f in fields if f in PII} | {"fin" for f in fields if f in FIN}
        columns = [self.identifier, self.table.c.anggota_id, self.table.c.protection_version]
        columns.extend(self.table.c[f"dek_{d}_wrapped"] for d in sorted(domains))
        columns.extend(self.table.c[f if f in REF else f + "_ct"] for f in sorted(fields))
        return columns

    def decode_many(self, rows, fields):
        if self.mode == "plain":
            return [{"anggota_id": str(row["id"]), **{f: text_value(row[f]) for f in fields}} for row in rows]
        domains = {"pii" for f in fields if f in PII} | {"fin" for f in fields if f in FIN}
        unwrapped = {}
        for domain in sorted(domains):
            wrapped = [r[f"dek_{domain}_wrapped"] for r in rows]
            if not wrapped:
                continue
            keys = self._crypto("unwrap_many", domain, wrapped)
            if len(keys) != len(rows):
                raise CryptoUnavailable("Incomplete unwrap batch")
            unwrapped[domain] = keys
        result = []
        for i, row in enumerate(rows):
            item = {"anggota_id": str(row["legacy_row_id"])}
            for field in fields:
                if field in REF:
                    value = text_value(row[field])
                else:
                    blob = row[field + "_ct"]
                    value = None if blob is None else self._crypto("decrypt_field", blob, unwrapped["fin" if field in FIN else "pii"][i],
                              anggota_id=str(row["anggota_id"]), column=field, protection_version=row["protection_version"])
                    if not isinstance(value, str) and blob is not None:
                        raise CryptoUnavailable("Invalid decrypted type")
                item[field] = value
            result.append(item)
        return result

    def list(self, db, user, page, size, lookup=None):
        condition = [self.scope(user)]
        if lookup:
            field, value = lookup
            if self.mode == "protected":
                condition.append(self.table.c[field + "_bidx"] == self._crypto("blind_index", field, value))
            elif field == "email":
                condition.append(func.lower(func.trim(self.table.c.email)) == normalized(field, value))
            else:
                condition.append(self.table.c[field] == normalized(field, value))
        count = db.scalar(select(func.count()).select_from(self.table).where(*condition))
        rows = db.execute(select(*self.projection({"nama"})).where(*condition).order_by(self.identifier).offset((page-1)*size).limit(size)).mappings().all()
        return self.decode_many(rows, {"nama"}), count

    def detail(self, db, user, identifier, fields, lock=False):
        query = select(*self.projection(fields)).where(self.identifier == identifier, self.scope(user))
        if lock:
            query = query.with_for_update()
        row = db.execute(query).mappings().first()
        return (self.decode_many([row], fields)[0], row) if row else (None, None)

    def patch(self, db, user, identifier, changes):
        # Lock and project only changed fields + required wrapping metadata; no FIN decryption.
        columns = [self.identifier] if self.mode == "plain" else [self.identifier, self.table.c.anggota_id, self.table.c.protection_version, self.table.c.dek_pii_wrapped]
        row = db.execute(select(*columns).where(self.identifier == identifier, self.scope(user, "update")).with_for_update()).mappings().first()
        if row is None:
            return False
        if self.mode == "plain":
            values = changes
        else:
            keys = self._crypto("unwrap_many", "pii", [row["dek_pii_wrapped"]])
            values = {}
            for field, value in changes.items():
                values[field + "_ct"] = None if value is None else self._crypto("encrypt_field", value, keys[0],
                    anggota_id=str(row["anggota_id"]), column=field, protection_version=row["protection_version"])
                if field == "email":
                    values["email_bidx"] = None if value is None else self._crypto("blind_index", "email", value)
            values["updated_at"] = utcnow()
        db.execute(update(self.table).where(self.identifier == identifier, self.scope(user, "update")).values(**values))
        return True

    def insert(self, db, payload, user=None):
        source = {f: payload.get(f) for f in SOURCE_FIELDS}
        if self.mode == "plain":
            if source["no_ktp"] is not None:
                source["no_ktp"] = normalized("no_ktp", source["no_ktp"])
                if db.bind.dialect.name == "postgresql":
                    # Baseline schema belongs to C: serialize API writers for this
                    # identity without changing it or granting runtime DDL rights.
                    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
                               {"identity": source["no_ktp"]})
                if db.scalar(select(self.identifier).where(self.table.c.no_ktp == source["no_ktp"]).limit(1)) is not None:
                    raise DuplicateIdentity()
            # Actual team's baseline stores dates/integers in native PostgreSQL types.
            if db.bind.dialect.name != "postgresql":
                source = {k: text_value(v) for k, v in source.items()}
            return db.execute(self.table.insert().values(**source).returning(self.identifier)).scalar_one()
        if user is None or not db.scalar(select(scopes.c.scope_id).where(scopes.c.principal == user.id,
                scopes.c.permission == "insert", scopes.c.anggota_id.is_(None)).limit(1)):
            return None
        # A's RLS hides unassigned IDs: MAX(id) cannot allocate a globally unique locator.
        # B's setup creates this separate sequence after migration, never resets an existing one.
        if db.bind.dialect.name == "postgresql":
            identifier = db.scalar(text("SELECT nextval('service_legacy_id_seq')"))
        else:
            identifier = db.scalar(select(func.coalesce(func.max(self.identifier), 0) + 1))
        record_id = str(uuid.uuid4())
        keys = self._crypto("new_record_keys")
        values = {"anggota_id": record_id, "legacy_row_id": identifier, "protection_version": 1,
                  "dek_pii_wrapped": keys["pii"][1], "dek_fin_wrapped": keys["fin"][1]}
        for field, raw in source.items():
            value = text_value(raw)
            if field in REF:
                values[field] = value
            else:
                domain = "fin" if field in FIN else "pii"
                values[field + "_ct"] = None if value is None else self._crypto("encrypt_field", value, keys[domain][0],
                                        anggota_id=record_id, column=field, protection_version=1)
            if field in {"no_ktp", "email", "pengguna"}:
                values[field + "_bidx"] = None if value is None else self._crypto("blind_index", field, value)
        born = payload.get("tanggal_lahir")
        if born:
            at = date(2026, 10, 1)
            age = at.year-born.year-((at.month, at.day) < (born.month, born.day))
            if age < 0:
                raise ValueError("Future birth date")
            start = age//10*10
            values["age_band"] = f"{start}-{start+9}"
        db.execute(self.table.insert().values(**values))
        return identifier
