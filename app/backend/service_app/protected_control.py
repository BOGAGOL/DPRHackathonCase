"""Mappings for A's account/scope/audit schema and B-owned session/binding tables."""
from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, LargeBinary, String, Table, Text, Uuid, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, column_property
from .models import utcnow


class ProtectedBase(DeclarativeBase):
    pass


bindings = Table("service_member_bindings", ProtectedBase.metadata,
    Column("user_id", Uuid(as_uuid=False), ForeignKey("app_users.user_id"), primary_key=True),
    Column("pengguna_bidx", LargeBinary, nullable=False))


class ProtectedUser(ProtectedBase):
    __tablename__ = "app_users"
    id: Mapped[str] = mapped_column("user_id", Uuid(as_uuid=False), primary_key=True)
    username: Mapped[str] = mapped_column(String(150), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(32))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    binding = column_property(select(bindings.c.pengguna_bidx).where(bindings.c.user_id == id).correlate_except(bindings).scalar_subquery())

    @property
    def principal(self):
        return "bidx:v1:" + self.binding.hex() if self.binding is not None else ""


class ProtectedSession(ProtectedBase):
    __tablename__ = "service_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("app_users.user_id"), index=True)
    expires_at: Mapped[object] = mapped_column(DateTime, default=utcnow)


scopes = Table("access_scope", ProtectedBase.metadata,
    Column("scope_id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True),
    Column("principal", Uuid(as_uuid=False), nullable=False),
    Column("anggota_id", Uuid(as_uuid=False)), Column("permission", String(16), nullable=False),
    Column("source_label", String(16), default="manual"))

audit_table = Table("audit_log", ProtectedBase.metadata,
    Column("event_id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True),
    Column("occurred_at", DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")),
    Column("actor", Uuid(as_uuid=False)), Column("actor_role", String(32), server_default=text("'database'")),
    Column("action", String(64)), Column("anggota_id", Uuid(as_uuid=False)),
    Column("field_class", String(16)), Column("decision", String(16)), Column("request_id", Uuid(as_uuid=False)))
