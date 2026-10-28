from datetime import datetime, timezone
import uuid

from sqlalchemy import JSON, Boolean, Column, Date, DateTime, ForeignKey, Integer, LargeBinary, SmallInteger, String, Table, Text, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SOURCE_FIELDS = "nama nama_lengkap nama_tanpa_gelar jenis_kelamin tempat_lahir tanggal_lahir tanggal_pernikahan no_ktp pekerjaan_terakhir alamat_jakarta telpon_jakarta alamat_daerah telpon_daerah handphone email ruangan status_kawin jumlah_anak jumlah_tanggungan jumlah_jiwa rekening nama_rekening npwp nama_kppn nip_kppn nama_bank kode_bank pengguna agama".split()
REF = {"jenis_kelamin", "pekerjaan_terakhir", "nama_kppn", "nama_bank"}
FIN = {"rekening", "nama_rekening", "npwp", "kode_bank"}
PII = set(SOURCE_FIELDS) - REF - FIN


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


def source_type(field):
    if field in {"tanggal_lahir", "tanggal_pernikahan"}:
        return Date().with_variant(Text(), "sqlite")
    if field.startswith("jumlah_"):
        return SmallInteger().with_variant(Text(), "sqlite")
    return Text()


baseline_members = Table("anggota", Base.metadata, Column("id", Integer, primary_key=True),
                         *(Column(f, source_type(f), nullable=f != "nama") for f in SOURCE_FIELDS))
protected_members = Table("anggota_protected", Base.metadata,
    Column("anggota_id", Uuid(as_uuid=False), primary_key=True), Column("legacy_row_id", Integer, nullable=False, unique=True),
    Column("protection_version", Integer, nullable=False), Column("dek_pii_wrapped", Text, nullable=False),
    Column("dek_fin_wrapped", Text, nullable=False), *(Column(f + "_ct", LargeBinary) for f in sorted(PII | FIN)),
    *(Column(f, Text) for f in sorted(REF | {"age_band"})),
    *(Column(f + "_bidx", LargeBinary, index=True) for f in ["no_ktp", "email", "pengguna"]),
    Column("created_at", DateTime, default=utcnow), Column("updated_at", DateTime, default=utcnow))


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(32))
    principal: Mapped[str] = mapped_column(String(100))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Session(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str | None] = mapped_column(String(36))
    role: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(64))
    anggota_id: Mapped[str | None] = mapped_column(String(36))
    field_class: Mapped[list] = mapped_column(JSON, default=list)
    decision: Mapped[str] = mapped_column(String(16))
    request_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
