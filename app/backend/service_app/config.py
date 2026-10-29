import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.engine import make_url


@dataclass
class Settings:
    mode: str
    database_url: str = field(repr=False)
    auth_database_url: str | None = field(default=None, repr=False)
    analyst_database_url: str | None = field(default=None, repr=False)
    auditor_database_url: str | None = field(default=None, repr=False)
    app_origin: str = "https://localhost:3443"
    session_ttl: int = 900
    testing: bool = False
    allow_disposable_database: bool = False
    openbao_addr: str = ""
    openbao_token: str = field(default="", repr=False)
    openbao_cacert: str = ""
    crypto_factory: str = "dprcrypto:public-v1"
    restored_database: str | None = None
    benchmark_database: str | None = None

    def validate(self):
        if self.mode not in {"plain", "protected"} or not 60 <= self.session_ttl <= 1800:
            raise ValueError("Invalid service mode/session lifetime")
        if not self.app_origin.startswith("https://"):
            raise ValueError("Browser origin must use HTTPS")
        if self.benchmark_database is not None:
            if self.restored_database is not None or not re.fullmatch(r"api_[a-z0-9_]{1,59}", self.benchmark_database):
                raise ValueError("Select one reserved api_ benchmark clone, separate from recovery")
        if self.testing:
            return self
        if self.restored_database is not None:
            if (self.mode != "protected" or not re.fullmatch(r"dpr_restore_[0-9a-f]{32}", self.restored_database)
                    or make_url(self.database_url).database != self.restored_database):
                raise ValueError("Select exactly one reserved restored database in protected mode")
        expected = {"baseline_100k", "baseline_1m"} if self.mode == "plain" else {"protected_100k", "protected_734", "protected_1m"}
        if self.restored_database:
            expected = {self.restored_database}
        if self.benchmark_database:
            expected = {self.benchmark_database}
        for value, role in [(self.database_url, "app_user"), (self.auth_database_url, "app_user"),
                            (self.analyst_database_url, "analyst_user"), (self.auditor_database_url, "auditor_user")]:
            if value is None:
                continue
            url = make_url(value)
            lab = self.allow_disposable_database and not self.benchmark_database and not self.restored_database and str(url.database).startswith("dpr_b_test_")
            if url.get_backend_name() != "postgresql" or (url.database not in expected and not lab):
                raise ValueError("Service may only connect to its authorized baseline/protected database")
            if url.username != role or url.query.get("sslmode") != "verify-full" or not url.query.get("sslrootcert"):
                raise ValueError("Least-privilege identity and verified PostgreSQL TLS are required")
            if not Path(url.query["sslrootcert"]).is_file():
                raise ValueError("PostgreSQL trusted CA file unavailable")
            if (self.mode == "protected" or self.benchmark_database) and (url.host, url.port, url.database) != (make_url(self.database_url).host, make_url(self.database_url).port, make_url(self.database_url).database):
                raise ValueError("Protected auth, audit and data must share the same target")
        return self

    @classmethod
    def from_env(cls):
        # Deliberately no root .env autoload; Module B does not inherit old lab/owner credentials.
        return cls(mode=os.environ["MODE"], database_url=os.environ["DATABASE_URL"],
                   auth_database_url=os.getenv("AUTH_DATABASE_URL"), analyst_database_url=os.getenv("ANALYST_DATABASE_URL"),
                   auditor_database_url=os.getenv("AUDITOR_DATABASE_URL"), app_origin=os.getenv("APP_ORIGIN", "https://localhost:3443"),
                   session_ttl=int(os.getenv("SESSION_TTL_SECONDS", "900")),
                   allow_disposable_database=os.getenv("DPR_ALLOW_DISPOSABLE_DATABASE") == "1",
                   openbao_addr=os.getenv("OPENBAO_ADDR", ""), openbao_token=os.getenv("OPENBAO_TOKEN", ""),
                   openbao_cacert=os.getenv("OPENBAO_CACERT", ""), crypto_factory=os.getenv("DPR_CRYPTO_FACTORY", "dprcrypto:public-v1"),
                   restored_database=os.getenv("DPR_RESTORED_DATABASE") or None,
                   benchmark_database=os.getenv("DPR_BENCHMARK_DATABASE") or None).validate()
