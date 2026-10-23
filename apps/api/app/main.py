import hashlib
import hmac
import secrets
import threading
import time
import uuid
from collections import defaultdict, deque
from typing import Annotated, Literal

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, delete, func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session as DBSession, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from .config import Settings
from .crypto import ProtectionError, build_protection
from .models import Assignment, AuditEvent, Member, Session, User, utcnow
from .policy import CONTACT, editable_fields, has, masked, member_scope, readable_fields
from .schemas import (AuditPage, AuditView, ContactPatch, DashboardView, KtpSearch, LoginInput,
                      MemberDetail, MemberPage, MemberSummary, Message, UserAccess, UserCreate, UserView)

PASSWORDS = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
# Random dummy hash equalizes work for unknown account names; no static credential.
DUMMY_HASH = PASSWORDS.hash(secrets.token_urlsafe(32))


def digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


class Limiter:
    """Bounded single-process limiter. Use shared enforcement before multi-worker deployment."""
    def __init__(self):
        self.entries = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key, limit, window=60):
        with self.lock:
            now = time.monotonic()
            if len(self.entries) > 10000:
                self.entries = defaultdict(deque, {k: v for k, v in self.entries.items() if v and v[-1] > now-window})
                if len(self.entries) > 10000:
                    return False
            queue = self.entries[key]
            while queue and queue[0] <= now-window:
                queue.popleft()
            if len(queue) >= limit:
                return False
            queue.append(now)
            return True


def create_app(settings: Settings | None = None):
    from datetime import timedelta
    settings = settings or Settings.from_env()
    engine = create_engine(settings.database_url, pool_pre_ping=True,
                           hide_parameters=True,
                           connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {})
    factory = sessionmaker(engine, expire_on_commit=False)
    protection = build_protection(settings)
    app = FastAPI(title="DPR Secure Data Management System", version="0.1.0",
                  docs_url="/docs" if settings.environment == "development" else None,
                  redoc_url=None, openapi_url="/openapi.json" if settings.environment == "development" else None)
    app.state.engine, app.state.session_factory, app.state.protection = engine, factory, protection
    app.state.settings = settings
    limiter = Limiter()

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        request.state.correlation_id = str(uuid.uuid4())
        if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
            # Only the configured browser origin, or non-browser clients with a CSRF cookie/header.
            origin = request.headers.get("origin")
            if origin is not None and origin != settings.app_origin:
                return JSONResponse({"detail": "Request ditolak"}, status_code=403, headers={"Cache-Control": "no-store"})
            size = request.headers.get("content-length", "0")
            if not size.isdigit() or int(size) > 32768:
                return JSONResponse({"detail": "Request terlalu besar"}, status_code=413)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Request-ID"] = request.state.correlation_id
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Pydantic's default errors echo input values; sensitive input must never be echoed.
        return JSONResponse({"detail": "Input tidak valid. Periksa format dan panjang field."}, status_code=422)

    @app.exception_handler(ProtectionError)
    async def crypto_error(request, exc):
        return JSONResponse({"detail": "Data terlindungi sementara tidak tersedia"}, status_code=503)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        return JSONResponse({"detail": "Layanan data sementara tidak tersedia"}, status_code=503)

    def db():
        with factory() as session:
            yield session

    DB = Annotated[DBSession, Depends(db)]

    def audit(session, request, actor, event, result="allowed", resource=None, fields=None):
        session.add(AuditEvent(actor_id=actor.id if actor else None, event_type=event,
                               resource_id=resource, result=result, fields=fields or [],
                               correlation_id=request.state.correlation_id))
        session.commit()

    def authenticated(request: Request, session: DB):
        token = request.cookies.get("dpr_session", "")
        entry = session.get(Session, digest(token)) if token else None
        user = session.get(User, entry.user_id) if entry and entry.expires_at > utcnow() else None
        if not user or not user.active:
            audit(session, request, None, "auth.required", "denied")
            raise HTTPException(401, "Silakan masuk kembali")
        request.state.auth_session = entry
        return user

    Auth = Annotated[User, Depends(authenticated)]

    def csrf(request: Request):
        header = request.headers.get("x-csrf-token", "")
        cookie = request.cookies.get("dpr_csrf", "")
        if len(header) < 32 or not hmac.compare_digest(header, cookie):
            raise HTTPException(403, "Request ditolak")
        entry = getattr(request.state, "auth_session", None)
        if entry and not hmac.compare_digest(entry.csrf_hash, digest(header)):
            raise HTTPException(403, "Request ditolak")

    def require(user, permission, session, request):
        if not has(user, permission):
            audit(session, request, user, permission, "denied")
            raise HTTPException(403, "Akses tidak diizinkan")

    def get_member(member_id, user, session, request):
        member = session.scalar(select(Member).where(Member.id == member_id, member_scope(user)))
        if not member:
            audit(session, request, user, "member.read", "denied", member_id)
            raise HTTPException(404, "Anggota tidak ditemukan")
        return member

    def summary(member):
        return MemberSummary(id=member.id, nama=member.nama, ruangan=member.ruangan)

    def detail(member, user):
        fields, hidden = {}, []
        for field in sorted(readable_fields(user)):
            fields[field] = protection.decrypt(member.id, field, member.protected_fields.get(field))
        if user.role == "operator":
            for field in sorted(CONTACT):
                fields[field] = masked(protection.decrypt(member.id, field, member.protected_fields.get(field)), field)
                hidden.append(field)
        return MemberDetail(**summary(member).model_dump(), fields=fields, masked_fields=hidden,
                            editable_fields=sorted(editable_fields(user)), revision=member.revision)

    def user_view(user):
        return UserView(id=user.id, username=user.username, role=user.role,
                        permissions=sorted(p for p in user.permissions if has(user, p)))

    def set_cookie(response, name, value, httponly, max_age=None):
        response.set_cookie(name, value, httponly=httponly, secure=settings.cookie_secure,
                            samesite="strict", max_age=max_age or settings.session_ttl, path="/")

    @app.get("/health/live", response_model=Message)
    def live():
        return Message(message="ok")

    @app.get("/health/ready", response_model=Message)
    def ready(session: DB):
        session.execute(text("SELECT 1"))
        session.execute(select(Member.id).limit(1))
        return Message(message="ready")

    @app.get("/auth/csrf", response_model=Message)
    def issue_csrf(request: Request, response: Response):
        # Do not rotate an authenticated session's bound CSRF token.
        token = request.cookies.get("dpr_csrf")
        if not request.cookies.get("dpr_session") or not token:
            set_cookie(response, "dpr_csrf", secrets.token_urlsafe(32), False)
        return Message(message="CSRF siap")

    @app.post("/auth/login", response_model=UserView)
    def login(payload: LoginInput, request: Request, response: Response, session: DB):
        csrf(request)
        peer = request.client.host if request.client else "unknown"
        if not limiter.allow("login-ip:" + digest(peer), 30, 300) or not limiter.allow("login-user:" + digest(payload.username), 10, 300):
            audit(session, request, None, "auth.login", "denied")
            raise HTTPException(429, "Coba kembali beberapa saat lagi")
        user = session.scalar(select(User).where(User.username == payload.username))
        try:
            valid = PASSWORDS.verify(user.password_hash if user else DUMMY_HASH, payload.password)
        except (VerificationError, InvalidHashError):
            valid = False
        if not valid or not user or not user.active:
            audit(session, request, None, "auth.login", "denied")
            raise HTTPException(401, "Username atau password tidak sesuai")
        previous = request.cookies.get("dpr_session")
        if previous:
            session.execute(delete(Session).where(Session.token_hash == digest(previous)))
        token, csrf_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        session.add(Session(token_hash=digest(token), csrf_hash=digest(csrf_token), user_id=user.id,
                            expires_at=utcnow() + timedelta(seconds=settings.session_ttl)))
        if PASSWORDS.check_needs_rehash(user.password_hash):
            user.password_hash = PASSWORDS.hash(payload.password)
        audit(session, request, user, "auth.login")
        set_cookie(response, "dpr_session", token, True)
        set_cookie(response, "dpr_csrf", csrf_token, False)
        return user_view(user)

    @app.get("/auth/me", response_model=UserView)
    def me(user: Auth):
        return user_view(user)

    @app.post("/auth/logout", response_model=Message)
    def logout(request: Request, response: Response, user: Auth, session: DB):
        csrf(request)
        session.delete(request.state.auth_session)
        audit(session, request, user, "auth.logout")
        for cookie in ["dpr_session", "dpr_csrf"]:
            response.delete_cookie(cookie, path="/", secure=settings.cookie_secure, httponly=cookie == "dpr_session", samesite="strict")
        return Message(message="Berhasil keluar")

    @app.get("/dashboard/stats", response_model=DashboardView)
    def stats(user: Auth, session: DB):
        return DashboardView(visible_members=session.scalar(select(func.count()).select_from(Member).where(member_scope(user))),
                             assigned_members=session.scalar(select(func.count()).select_from(Assignment).where(Assignment.user_id == user.id)),
                             own_events=session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.actor_id == user.id)), role=user.role)

    @app.get("/anggota", response_model=MemberPage)
    def members(request: Request, user: Auth, session: DB, page: int = Query(1, ge=1, le=100000),
                page_size: int = Query(10, ge=1, le=50), q: str = Query("", max_length=120),
                sort: Literal["nama", "id", "ruangan"] = "nama", direction: Literal["asc", "desc"] = "asc"):
        condition = [member_scope(user)]
        if q:
            # Name search only; identifier exact lookup has a separate permission-controlled endpoint.
            condition.append(Member.nama.icontains(q, autoescape=True))
        total = session.scalar(select(func.count()).select_from(Member).where(*condition))
        column = {"nama": Member.nama, "id": Member.id, "ruangan": Member.ruangan}[sort]
        rows = session.scalars(select(Member).where(*condition).order_by(column.asc() if direction == "asc" else column.desc(), Member.id)
                               .offset((page-1)*page_size).limit(page_size)).all()
        audit(session, request, user, "member.list")
        return MemberPage(items=[summary(m) for m in rows], total=total, page=page, page_size=page_size)

    @app.post("/anggota/search/ktp", response_model=list[MemberSummary])
    def search(payload: KtpSearch, request: Request, user: Auth, session: DB):
        csrf(request)
        require(user, "search:ktp", session, request)
        if not limiter.allow(f"search:{user.id}", 20):
            audit(session, request, user, "member.search", "denied")
            raise HTTPException(429, "Batas pencarian tercapai")
        matches = session.scalars(select(Member).where(Member.ktp_index == protection.blind_index(payload.no_ktp), member_scope(user)).limit(50)).all()
        audit(session, request, user, "member.search")
        return [summary(member) for member in matches]

    @app.get("/anggota/{member_id}", response_model=MemberDetail)
    def member_detail(member_id: int, request: Request, user: Auth, session: DB):
        member = get_member(member_id, user, session, request)
        result = detail(member, user)
        audit(session, request, user, "member.read", resource=member_id)
        return result

    @app.patch("/anggota/{member_id}/contact", response_model=MemberDetail)
    def update_contact(member_id: int, payload: ContactPatch, request: Request, user: Auth, session: DB):
        csrf(request)
        member = get_member(member_id, user, session, request)
        changes = payload.model_dump(exclude_unset=True, exclude={"revision"})
        if not set(changes) <= editable_fields(user):
            audit(session, request, user, "member.update", "denied", member_id, sorted(changes))
            raise HTTPException(403, "Field tidak diizinkan")
        if payload.revision != member.revision:
            raise HTTPException(409, "Data telah berubah. Muat ulang profil.")
        encrypted = dict(member.protected_fields)
        for field, value in changes.items():
            encrypted[field] = protection.encrypt(member.id, field, value)
        member.protected_fields = encrypted
        try:
            session.flush()
            result = detail(member, user)
            audit(session, request, user, "member.update", resource=member_id, fields=sorted(changes))
        except StaleDataError:
            session.rollback()
            raise HTTPException(409, "Data telah berubah. Muat ulang profil.") from None
        return result

    @app.get("/audit/events", response_model=AuditPage)
    def events(request: Request, user: Auth, session: DB, page: int = Query(1, ge=1, le=100000)):
        require(user, "audit:read", session, request)
        rows = session.scalars(select(AuditEvent).order_by(AuditEvent.id.desc()).offset((page-1)*25).limit(25)).all()
        return AuditPage(items=[AuditView.model_validate(r, from_attributes=True) for r in rows],
                         total=session.scalar(select(func.count()).select_from(AuditEvent)), page=page)

    @app.get("/admin/users", response_model=list[UserView])
    def users(request: Request, user: Auth, session: DB):
        require(user, "users:manage", session, request)
        return [user_view(u) for u in session.scalars(select(User).order_by(User.id).limit(100))]

    @app.post("/admin/users", response_model=UserView, status_code=201)
    def create_user(payload: UserCreate, request: Request, user: Auth, session: DB):
        csrf(request)
        require(user, "users:manage", session, request)
        if len(set(payload.assignments)) != session.scalar(select(func.count()).select_from(Member).where(Member.id.in_(payload.assignments))):
            raise HTTPException(422, "Penugasan tidak valid")
        target = User(username=payload.username, password_hash=PASSWORDS.hash(payload.password), role=payload.role, permissions=payload.permissions)
        session.add(target)
        try:
            session.flush()
            session.add_all([Assignment(user_id=target.id, member_id=i) for i in set(payload.assignments)])
            audit(session, request, user, "user.create", resource=target.id)
        except IntegrityError:
            session.rollback()
            raise HTTPException(409, "Akun tidak dapat dibuat") from None
        return user_view(target)

    @app.patch("/admin/users/{user_id}/access", response_model=UserView)
    def update_user(user_id: int, payload: UserAccess, request: Request, user: Auth, session: DB):
        csrf(request)
        require(user, "users:manage", session, request)
        target = session.get(User, user_id)
        if not target:
            raise HTTPException(404, "Akun tidak ditemukan")
        if target.id == user.id:
            raise HTTPException(403, "Gunakan admin lain untuk perubahan akun sendiri")
        if len(set(payload.assignments)) != session.scalar(select(func.count()).select_from(Member).where(Member.id.in_(payload.assignments))):
            raise HTTPException(422, "Penugasan tidak valid")
        target.active, target.permissions = payload.active, payload.permissions
        session.execute(delete(Assignment).where(Assignment.user_id == target.id))
        session.execute(delete(Session).where(Session.user_id == target.id))
        session.add_all([Assignment(user_id=target.id, member_id=i) for i in set(payload.assignments)])
        audit(session, request, user, "user.access", resource=target.id)
        return user_view(target)

    return app
