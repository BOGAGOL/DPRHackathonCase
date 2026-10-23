from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .policy import ADDRESS, CONTACT, PERMISSIONS, ROLES


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Message(StrictModel):
    message: str


class LoginInput(StrictModel):
    username: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=1, max_length=256)


class UserView(StrictModel):
    id: int
    username: str
    role: str
    permissions: list[str]


class MemberSummary(StrictModel):
    id: int
    nama: str
    ruangan: str | None


class MemberDetail(MemberSummary):
    fields: dict[str, str | None]
    masked_fields: list[str]
    editable_fields: list[str]
    revision: int


class MemberPage(StrictModel):
    items: list[MemberSummary]
    total: int
    page: int
    page_size: int


class KtpSearch(StrictModel):
    no_ktp: str = Field(min_length=1, max_length=128)

    @field_validator("no_ktp")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("Nomor tidak boleh kosong")
        return value


class ContactPatch(StrictModel):
    revision: int = Field(ge=1)
    email: str | None = Field(default=None, max_length=254)
    handphone: str | None = Field(default=None, max_length=40)
    telpon_jakarta: str | None = Field(default=None, max_length=40)
    telpon_daerah: str | None = Field(default=None, max_length=40)
    alamat_jakarta: str | None = Field(default=None, max_length=1000)
    alamat_daerah: str | None = Field(default=None, max_length=1000)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value):
        import re
        if value is not None and value != "" and not re.fullmatch(r"[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+", value):
            raise ValueError("Email tidak valid")
        return value

    @field_validator("handphone", "telpon_jakarta", "telpon_daerah")
    @classmethod
    def validate_phone(cls, value):
        import re
        if value is not None and not re.fullmatch(r"[0-9+() .-]*", value):
            raise ValueError("Telepon tidak valid")
        return value

    @model_validator(mode="after")
    def changes_required(self):
        if not (self.model_fields_set & (CONTACT | ADDRESS)):
            raise ValueError("Tidak ada perubahan")
        return self


class AuditView(StrictModel):
    id: int
    actor_id: int | None
    event_type: str
    resource_id: int | None
    result: str
    created_at: datetime
    correlation_id: str
    fields: list[str]


class AuditPage(StrictModel):
    items: list[AuditView]
    total: int
    page: int


class DashboardView(StrictModel):
    visible_members: int
    assigned_members: int
    own_events: int
    role: str


class UserCreate(LoginInput):
    password: str = Field(min_length=12, max_length=256)
    role: Literal["public", "operator", "staff", "admin"]
    permissions: list[str] = Field(default_factory=list, max_length=20)
    assignments: list[int] = Field(default_factory=list, max_length=1000)

    @field_validator("permissions")
    @classmethod
    def known_permissions(cls, value):
        if not set(value) <= PERMISSIONS:
            raise ValueError("Unknown permission")
        return sorted(set(value))


class UserAccess(StrictModel):
    active: bool
    permissions: list[str] = Field(max_length=20)
    assignments: list[int] = Field(max_length=1000)

    _known_permissions = field_validator("permissions")(UserCreate.known_permissions.__func__)
