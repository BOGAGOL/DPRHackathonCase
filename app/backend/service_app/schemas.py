from datetime import date, datetime
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Message(Strict):
    message: str


class Login(Strict):
    username: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=1, max_length=256)


class UserDTO(Strict):
    id: str
    username: str
    role: str


class Summary(Strict):
    anggota_id: str
    nama: str | None


class MemberPage(Strict):
    items: list[Summary]
    total: int
    page: int
    page_size: int


class OperatorDetail(Summary):
    no_ktp: str | None
    email: str | None
    handphone: str | None
    telpon_jakarta: str | None
    telpon_daerah: str | None


class PrivilegedDetail(OperatorDetail):
    nama_lengkap: str | None
    nama_tanpa_gelar: str | None
    jenis_kelamin: str | None
    tempat_lahir: str | None
    tanggal_lahir: str | None
    tanggal_pernikahan: str | None
    pekerjaan_terakhir: str | None
    alamat_jakarta: str | None
    alamat_daerah: str | None
    ruangan: str | None
    status_kawin: str | None
    jumlah_anak: str | None
    jumlah_tanggungan: str | None
    jumlah_jiwa: str | None
    nama_kppn: str | None
    nip_kppn: str | None
    nama_bank: str | None
    pengguna: str | None
    agama: str | None


class FinanceDetail(Summary):
    no_ktp: str | None
    rekening: str | None
    nama_rekening: str | None
    npwp: str | None
    kode_bank: str | None
    nama_bank: str | None
    nama_kppn: str | None


MemberDetail = OperatorDetail | PrivilegedDetail | FinanceDetail


def email_check(value):
    if value is not None and value != "" and not re.fullmatch(r"[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+", value):
        raise ValueError("Invalid email")
    return value


def phone_check(value):
    if value and (not re.fullmatch(r"[0-9+() .-]{1,20}", value) or not any(c.isdigit() for c in value)):
        raise ValueError("Invalid phone")
    return value


def ktp_check(value):
    if value is not None and not re.fullmatch(r"(?:[0-9]{14}|[0-9]{16})", value):
        raise ValueError("Expected synthetic 14-digit or 16-digit identifier")
    return value


class ContactPatch(Strict):
    email: str | None = Field(default=None, max_length=150)
    handphone: str | None = Field(default=None, max_length=20)
    _email = field_validator("email")(email_check)
    _phone = field_validator("handphone")(phone_check)

    @model_validator(mode="after")
    def nonempty(self):
        if not self.model_fields_set:
            raise ValueError("No changes")
        return self


class MemberInsert(Strict):
    nama: str = Field(min_length=1, max_length=100)
    pengguna: str = Field(min_length=1, max_length=100)
    nama_lengkap: str | None = Field(default=None, max_length=100)
    nama_tanpa_gelar: str | None = Field(default=None, max_length=100)
    jenis_kelamin: str | None = Field(default=None, pattern="^[LP]$")
    tempat_lahir: str | None = Field(default=None, max_length=50)
    tanggal_lahir: date | None = None
    tanggal_pernikahan: date | None = None
    no_ktp: str | None = Field(default=None, max_length=20)
    pekerjaan_terakhir: str | None = Field(default=None, max_length=50)
    alamat_jakarta: str | None = Field(default=None, max_length=255)
    alamat_daerah: str | None = Field(default=None, max_length=255)
    telpon_jakarta: str | None = Field(default=None, max_length=20)
    telpon_daerah: str | None = Field(default=None, max_length=20)
    handphone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=150)
    ruangan: str | None = Field(default=None, max_length=20)
    status_kawin: str | None = Field(default=None, max_length=2)
    jumlah_anak: int | None = Field(default=None, ge=0, le=32767)
    jumlah_tanggungan: int | None = Field(default=None, ge=0, le=32767)
    jumlah_jiwa: int | None = Field(default=None, ge=0, le=32767)
    rekening: str | None = Field(default=None, max_length=30)
    nama_rekening: str | None = Field(default=None, max_length=100)
    npwp: str | None = Field(default=None, max_length=20)
    nama_kppn: str | None = Field(default=None, max_length=50)
    nip_kppn: str | None = Field(default=None, max_length=20)
    nama_bank: str | None = Field(default=None, max_length=50)
    kode_bank: str | None = Field(default=None, max_length=5)
    agama: str | None = Field(default=None, max_length=20)
    _email = field_validator("email")(email_check)
    _phone = field_validator("handphone", "telpon_jakarta", "telpon_daerah")(phone_check)
    _ktp = field_validator("no_ktp")(ktp_check)

    @model_validator(mode="after")
    def valid_birth_date(self):
        if self.tanggal_lahir and self.tanggal_lahir > date(2026, 10, 1):
            raise ValueError("Birth date exceeds frozen dataset reference date")
        return self


class AuditDTO(Strict):
    id: int
    actor: str | None
    role: str
    action: str
    anggota_id: str | None
    field_class: list[str]
    decision: str
    request_id: str | None
    created_at: datetime


class AuditPage(Strict):
    items: list[AuditDTO]
    total: int
    page: int
    page_size: int


class AggregateGroup(Strict):
    dimension: str
    value: str | None
    count: int | Literal["<5"] | None


class Analytics(Strict):
    total: int | Literal["<5"] | None
    groups: list[AggregateGroup]


class AnalyticsFilters(Strict):
    jenis_kelamin: Literal["L", "P"] | None = None
    pekerjaan_terakhir: str | None = Field(default=None, min_length=1, max_length=50)
    nama_kppn: str | None = Field(default=None, min_length=1, max_length=50)
    nama_bank: str | None = Field(default=None, min_length=1, max_length=50)
    age_band: str | None = Field(default=None, pattern=r"^[0-9]{1,3}-[0-9]{1,3}$")
