from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import timedelta
import hashlib
import hmac
from pathlib import Path
import secrets
import threading
import time
import uuid

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, delete, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from .config import Settings
from .crypto import CryptoUnavailable, ToolkitAdapter
from .models import AuditLog, Session as PlainSession, User as PlainUser, protected_members, utcnow
from .protected_control import ProtectedUser, ProtectedSession, audit_table
from .analytics import summary
from .recovery import verify_restore_target
from .policy import ROLES, can_access, detail_policy, mask, mask_list_name
from .repository import MemberRepository, normalized
from .schemas import (Analytics, AuditDTO, AuditPage, ContactPatch, FinanceDetail, Login, MemberDetail,
                      MemberInsert, MemberPage, Message, OperatorDetail, PrivilegedDetail, UserDTO, AnalyticsFilters, email_check, ktp_check)

PASSWORDS = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
DUMMY_HASH = PASSWORDS.hash(secrets.token_urlsafe(32))


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class LoginLimiter:
    def __init__(self):
        self.buckets = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key, limit):
        with self.lock:
            now = time.monotonic()
            if len(self.buckets) > 10000:
                self.buckets = defaultdict(deque, {k: v for k, v in self.buckets.items() if v and v[-1] > now-300})
                if len(self.buckets) > 10000:
                    return False
            bucket = self.buckets[key]
            while bucket and bucket[0] <= now-300:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            return True


def create_app(settings=None, crypto=None):
    settings = (settings or Settings.from_env()).validate()
    if crypto is not None and not settings.testing:
        raise ValueError("Injecting a test crypto driver is forbidden outside tests")
    if settings.mode == "protected" and not settings.testing:
        root = Path(__file__).resolve().parents[3]
        if not all(p.exists() for p in [root / "toolkit/dprcrypto", root / "policy/protection_profile.yaml", root / "docs/contracts/test_vectors.json"]):
            raise CryptoUnavailable("Module A toolkit, profile and shared test vectors are required")
    protection = crypto if settings.mode == "protected" and crypto is not None else ToolkitAdapter(settings) if settings.mode == "protected" else None
    User = ProtectedUser if settings.mode == "protected" else PlainUser
    Session = ProtectedSession if settings.mode == "protected" else PlainSession
    repository = MemberRepository(settings.mode, protection, settings.testing)
    engines = {}
    def engine_for(url):
        if not url:
            return None
        if url not in engines:
            engines[url] = create_engine(url, hide_parameters=True, pool_pre_ping=True,
                connect_args={"check_same_thread": False} if url.startswith("sqlite") else {"connect_timeout": 10})
        return engines[url]
    data_engine = engine_for(settings.database_url)
    auth_engine = engine_for(settings.auth_database_url or settings.database_url)
    analyst_engine = engine_for(settings.analyst_database_url or (settings.database_url if settings.testing else None))
    auditor_engine = engine_for(settings.auditor_database_url or (settings.auth_database_url or settings.database_url if settings.testing else None))
    if settings.restored_database and not settings.testing:
        try:
            with data_engine.begin() as connection:
                verify_restore_target(connection, settings.restored_database)
        except Exception:
            for engine in engines.values():
                engine.dispose()
            if protection is not None:
                protection.close()
            raise ValueError("Verified service restore target unavailable") from None
    data_factory = sessionmaker(data_engine, expire_on_commit=False)
    auth_factory = sessionmaker(auth_engine, expire_on_commit=False)
    @asynccontextmanager
    async def lifespan(application):
        yield
        if protection is not None and callable(getattr(protection, "close", None)):
            protection.close()
        for engine in engines.values():
            engine.dispose()
    app = FastAPI(title="DPR Service Application — Module B", version="1.1.0", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.User, app.state.Session = User, Session
    app.state.engine, app.state.data_factory = data_engine, data_factory
    app.state.auth_engine, app.state.auth_factory = auth_engine, auth_factory
    app.state.protection, app.state.settings = protection, settings
    app.state.session_factory = auth_factory
    limiter = LoginLimiter()

    def audit(request, user, action, decision="allowed", identifier=None, classes=None, db=None):
        if settings.mode == "protected":
            def append(connection):
                if user:
                    principal(connection, user)
                record_id = connection.scalar(select(protected_members.c.anggota_id).where(protected_members.c.legacy_row_id == int(identifier))) if identifier is not None else None
                for field_class in sorted(classes or ["AUTH"]):
                    values = dict(action=action, anggota_id=record_id, field_class=field_class,
                                  decision="error" if decision == "failed" else decision, request_id=request.state.request_id)
                    if connection.bind.dialect.name == "sqlite":
                        # SQLite fixture has no A audit-context trigger.
                        values.update(actor=user.id if user else None, actor_role=user.role if user else "anonymous")
                    connection.execute(audit_table.insert().values(**values).inline())
            if db is not None:
                append(db)
            else:
                with auth_factory.begin() as log_db:
                    append(log_db)
            return
        event = AuditLog(actor=user.id if user else None, role=user.role if user else "anonymous", action=action,
                         anggota_id=str(identifier) if identifier is not None else None, field_class=sorted(classes or []),
                         decision=decision, request_id=request.state.request_id)
        if db is not None and data_engine is auth_engine:
            db.add(event)
        else:
            with auth_factory.begin() as log_db:
                log_db.add(event)

    @app.middleware("http")
    async def headers(request: Request, call_next):
        request.state.request_id = str(uuid.uuid4())
        response = None
        if request.method in {"POST", "PATCH", "PUT", "DELETE"} and request.headers.get("origin", settings.app_origin) != settings.app_origin:
            response = JSONResponse({"detail": "Request ditolak"}, status_code=403)
        else:
            if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
                collected = bytearray()
                async for part in request.stream():
                    if len(collected)+len(part) > 32768:
                        response = JSONResponse({"detail": "Request terlalu besar"}, status_code=413)
                        break
                    collected.extend(part)
                if response is None:
                    request._body = bytes(collected)
            if response is None:
                response = await call_next(request)
        response.headers.update({"Cache-Control": "no-store", "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
                                 "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY", "X-Request-ID": request.state.request_id})
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, exc):
        return JSONResponse({"detail": "Input tidak valid"}, status_code=422)

    @app.exception_handler(CryptoUnavailable)
    async def crypto_failure(request, exc):
        audit(request, getattr(request.state, "user", None), "decrypt", "failed", getattr(request.state, "resource_id", None), getattr(request.state, "field_classes", ["PII"]))
        return JSONResponse({"detail": "Operasi data gagal"}, status_code=500)

    @app.exception_handler(SQLAlchemyError)
    async def db_failure(request, exc):
        return JSONResponse({"detail": "Layanan data tidak tersedia"}, status_code=503)

    def principal(db, user):
        if db.bind.dialect.name == "postgresql":
            # set_config(..., true) is parameterized SET LOCAL and resets on transaction end.
            db.execute(text("SELECT set_config('app.principal', :principal, true), set_config('app.role', :role, true), set_config('app.actor', :actor, true)"),
                       {"principal": user.id if settings.mode == "protected" else user.principal, "role": user.role, "actor": user.id})

    def auth(request: Request):
        token = request.cookies.get("dpr_session")
        with auth_factory() as db:
            entry = db.get(Session, digest(token)) if token else None
            user = db.get(User, entry.user_id) if entry and entry.expires_at > utcnow() else None
            if not user or not user.active or user.role not in ROLES:
                audit(request, None, "auth.required", "denied")
                raise HTTPException(401, "Silakan masuk kembali")
            request.state.user, request.state.session = user, entry
            return user

    def csrf(request):
        cookie, header = request.cookies.get("dpr_csrf", ""), request.headers.get("x-csrf-token", "")
        session = getattr(request.state, "session", None)
        if len(cookie) < 32 or not hmac.compare_digest(cookie, header) or (session and not hmac.compare_digest(digest(header), session.csrf_hash)):
            audit(request, getattr(request.state, "user", None), "csrf", "denied")
            raise HTTPException(403, "Request ditolak")

    def allowed(request, user, action):
        if not can_access(user.role, action):
            audit(request, user, action, "denied")
            raise HTTPException(403, "Akses tidak diizinkan")

    def classes(fields):
        from .models import FIN, PII
        return ({"PII"} if set(fields) & PII else set()) | ({"FIN"} if set(fields) & FIN else set()) | ({"REF"} if set(fields) - PII - FIN else set())

    def dto(member, user):
        policy = detail_policy(user.role)
        result = {**member, **{f: mask(member[f], f) for f in policy.masked}}
        cls = OperatorDetail if user.role == "operator" else FinanceDetail if user.role == "finance_officer" else PrivilegedDetail
        return cls.model_validate(result)

    def detail(db, request, user, identifier):
        request.state.resource_id = str(identifier)
        policy = detail_policy(user.role)
        request.state.field_classes = sorted(classes(policy.fields) - {"REF"})
        member, _ = repository.detail(db, user, identifier, policy.fields)
        if member is None:
            audit(request, user, "detail", "denied", identifier)
            raise HTTPException(404, "Anggota tidak ditemukan")
        audit(request, user, "detail", identifier=identifier, classes=classes(policy.fields), db=db)
        if settings.mode == "protected":
            audit(request, user, "decrypt", identifier=identifier, classes=classes(policy.fields) - {"REF"}, db=db)
        return dto(member, user)

    def cookie(response, name, value, httponly):
        response.set_cookie(name, value, secure=True, httponly=httponly, samesite="strict", path="/", max_age=settings.session_ttl)

    @app.get("/health/live", response_model=Message)
    def live():
        return Message(message="ok")

    @app.get("/health/ready", response_model=Message)
    def ready():
        with data_engine.connect() as db:
            db.execute(select(repository.identifier).limit(1))
        return Message(message="ready")

    @app.get("/auth/csrf", response_model=Message)
    def issue_csrf(request: Request, response: Response):
        if not request.cookies.get("dpr_session") or not request.cookies.get("dpr_csrf"):
            cookie(response, "dpr_csrf", secrets.token_urlsafe(32), False)
        return Message(message="CSRF siap")

    @app.post("/auth/login", response_model=UserDTO)
    def login(payload: Login, request: Request, response: Response):
        csrf(request)
        peer = request.client.host if request.client else "unknown"
        if not limiter.allow("ip:"+digest(peer), 60) or not limiter.allow("account:"+digest(payload.username), 10):
            audit(request, None, "login", "denied")
            raise HTTPException(429, "Coba kembali beberapa saat lagi")
        with auth_factory.begin() as db:
            user = db.scalar(select(User).where(User.username == payload.username))
            try:
                valid = PASSWORDS.verify(user.password_hash if user else DUMMY_HASH, payload.password)
            except VerificationError:
                valid = False
            if not valid or not user or not user.active or user.role not in ROLES:
                audit(request, None, "login", "denied")
                raise HTTPException(401, "Username atau password tidak sesuai")
            old = request.cookies.get("dpr_session")
            if old:
                db.execute(delete(Session).where(Session.token_hash == digest(old)))
            token, csrf_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            db.add(Session(token_hash=digest(token), csrf_hash=digest(csrf_token), user_id=user.id, expires_at=utcnow()+timedelta(seconds=settings.session_ttl)))
            if PASSWORDS.check_needs_rehash(user.password_hash):
                user.password_hash = PASSWORDS.hash(payload.password)
            # Same control transaction for session + its audit.
            audit(request, user, "login", db=db)
        cookie(response, "dpr_session", token, True)
        cookie(response, "dpr_csrf", csrf_token, False)
        return UserDTO(id=user.id, username=user.username, role=user.role)

    @app.get("/auth/me", response_model=UserDTO)
    def me(user=Depends(auth)):
        return UserDTO(id=user.id, username=user.username, role=user.role)

    @app.post("/auth/logout", response_model=Message)
    def logout(request: Request, response: Response, user=Depends(auth)):
        csrf(request)
        with auth_factory.begin() as db:
            db.execute(delete(Session).where(Session.token_hash == request.state.session.token_hash))
            audit(request, user, "logout", db=db)
        for name in ["dpr_session", "dpr_csrf"]:
            response.delete_cookie(name, path="/", secure=True, httponly=name == "dpr_session", samesite="strict")
        return Message(message="Berhasil keluar")

    def listing(request, user, page, lookup=None):
        allowed(request, user, "list")
        with data_factory() as db:
            principal(db, user)
            items, total = repository.list(db, user, page, 50, lookup)
            if mask_list_name(user.role):
                items = [{**row, "nama": mask(row["nama"], "nama")} for row in items]
            audit(request, user, "search" if lookup else "list", classes=["PII"], db=db)
            if settings.mode == "protected":
                for row in items:
                    audit(request, user, "decrypt", identifier=row["anggota_id"], classes=["PII"], db=db)
            db.commit()
        return MemberPage(items=items, page=page, page_size=50, total=total)

    @app.get("/anggota", response_model=MemberPage)
    def members(request: Request, page: int = Query(1, ge=1, le=1000000), user=Depends(auth)):
        return listing(request, user, page)

    @app.get("/anggota/search", response_model=MemberPage)
    def search(request: Request, no_ktp: str | None = Query(None, max_length=128), email: str | None = Query(None, max_length=150), user=Depends(auth)):
        allowed(request, user, "search")
        if (no_ktp is None) == (email is None):
            raise HTTPException(422, "Pilih tepat satu field pencarian")
        try:
            field, value = ("no_ktp", ktp_check(normalized("no_ktp", no_ktp))) if no_ktp is not None else ("email", email_check(normalized("email", email)))
            if not value:
                raise ValueError()
        except ValueError:
            raise HTTPException(422, "Input pencarian tidak valid") from None
        return listing(request, user, 1, (field, value))

    @app.get("/anggota/{anggota_id}", response_model=MemberDetail)
    def member(anggota_id: int, request: Request, user=Depends(auth)):
        allowed(request, user, "detail")
        with data_factory() as db:
            principal(db, user)
            result = detail(db, request, user, anggota_id)
            db.commit()
        return result

    @app.patch("/anggota/{anggota_id}/kontak", response_model=MemberDetail)
    def patch(anggota_id: int, payload: ContactPatch, request: Request, user=Depends(auth)):
        csrf(request)
        allowed(request, user, "update")
        request.state.resource_id = str(anggota_id)
        with data_factory() as db:
            principal(db, user)
            if not repository.patch(db, user, anggota_id, payload.model_dump(exclude_unset=True)):
                audit(request, user, "update", "denied", anggota_id)
                raise HTTPException(404, "Anggota tidak ditemukan")
            result = detail(db, request, user, anggota_id)
            audit(request, user, "update", identifier=anggota_id, classes=["PII"], db=db)
            db.commit()
        return result

    @app.post("/anggota", response_model=MemberDetail, status_code=201)
    def insert(payload: MemberInsert, request: Request, user=Depends(auth)):
        csrf(request)
        allowed(request, user, "insert")
        with data_factory() as db:
            principal(db, user)
            identifier = repository.insert(db, payload.model_dump(), user)
            if identifier is None:
                audit(request, user, "insert", "denied")
                raise HTTPException(403, "Akses tidak diizinkan")
            result = detail(db, request, user, identifier)
            audit(request, user, "insert", identifier=identifier, classes=["PII", "FIN", "REF"], db=db)
            db.commit()
        return result

    @app.get("/analytics/summary", response_model=Analytics)
    def analytics(request: Request, filters: AnalyticsFilters = Query(), user=Depends(auth)):
        allowed(request, user, "analytics")
        if analyst_engine is None:
            raise HTTPException(503, "Identitas analyst belum dikonfigurasi")
        with sessionmaker(analyst_engine)() as db:
            principal(db, user)
            result = summary(db, filters.model_dump(exclude_none=True))
        audit(request, user, "analytics", classes=["REF"])
        return Analytics(**result)

    @app.get("/audit", response_model=AuditPage)
    def events(request: Request, page: int = Query(1, ge=1, le=1000000), user=Depends(auth)):
        allowed(request, user, "audit")
        if auditor_engine is None:
            raise HTTPException(503, "Identitas auditor belum dikonfigurasi")
        with sessionmaker(auditor_engine)() as db:
            principal(db, user)
            if settings.mode == "protected":
                total = db.scalar(select(func.count()).select_from(audit_table))
                rows = db.execute(select(audit_table).order_by(audit_table.c.event_id.desc()).offset((page-1)*50).limit(50)).mappings()
                items = [AuditDTO(id=r["event_id"], actor=r["actor"], role=r["actor_role"], action=r["action"],
                    anggota_id=r["anggota_id"], field_class=[r["field_class"]], decision=r["decision"],
                    request_id=r["request_id"], created_at=r["occurred_at"]) for r in rows]
            else:
                total = db.scalar(select(func.count()).select_from(AuditLog))
                rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).offset((page-1)*50).limit(50)).all()
                items = [AuditDTO.model_validate(row, from_attributes=True) for row in rows]
        audit(request, user, "audit.read")
        return AuditPage(items=items, total=total, page=page, page_size=50)

    return app
