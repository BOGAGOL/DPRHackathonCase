"""Owned fresh services, random loopback ports and exclusive outside-repo storage."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import time

from infra.security import external_directory, secure_directory, write_private
from infra.tls.make_ca import make_ca
from infra.postgres.make_cert import make_certificate
from .bootstrap import ROOT


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def clean_environment():
    """Do not inherit a developer's DB, Bao, proxy or cloud credentials."""
    allowed = {"PATH", "SystemRoot", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "USERPROFILE", "HOME",
               "LOCALAPPDATA", "APPDATA", "TEMP", "TMP", "HOMEDRIVE", "HOMEPATH", "ProgramFiles",
               "PROGRAMFILES", "ProgramFiles(x86)", "PROGRAMFILES(X86)", "ProgramW6432",
               "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"}
    return {key: value for key, value in os.environ.items() if key in allowed}


@contextmanager
def environment(values):
    previous = dict(os.environ)
    sanitized = clean_environment()
    os.environ.clear()
    os.environ.update(sanitized)
    os.environ.update({key: str(value) for key, value in values.items()})
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(previous)


class Stack:
    def __init__(self, directory, *, pg_bin=None, bao_bin=None):
        directory = external_directory(str(directory))
        if directory.exists():
            raise ValueError("Reproduction requires a NEW private directory")
        if (pg_bin is None) != (bao_bin is None):
            raise ValueError("Both native executable paths are required")
        self.root = secure_directory(directory)
        self.pg_bin = pg_bin.resolve() if pg_bin else None
        self.bao_bin = bao_bin.resolve() if bao_bin else None
        self.project = "dpr-repro-" + secrets.token_hex(8)
        self.container = self.project + "-postgres-1"
        self.password = secrets.token_urlsafe(36)
        self.pg_started = False
        self.compose_started = False
        self.bao_process = None
        self.pg_port, self.bao_port = free_port(), free_port()
        while self.pg_port == self.bao_port:
            self.bao_port = free_port()
        self.child_env = {**clean_environment(), "DPR_SECRETS_DIR": str(self.root),
                          "DPR_REPRO_UID": str(getattr(os, "getuid", lambda: 1000)()),
                          "DPR_REPRO_GID": str(getattr(os, "getgid", lambda: 1000)())}
        if self.child_env["DPR_REPRO_UID"] == "0":
            raise ValueError("Run reproduction as a non-root operator")

    def executable(self, name):
        path = self.pg_bin / (name + (".exe" if os.name == "nt" else ""))
        if name not in {"postgres", "initdb", "pg_ctl", "psql", "pg_dump", "pg_restore"} or not path.is_file():
            raise ValueError("PostgreSQL binary unavailable")
        return str(path)

    def command(self, command, *, timeout=180, input=None, env=None, quiet=False):
        output = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL} if quiet else {"capture_output": True}
        result = subprocess.run(command, input=input, env=env or self.child_env,
                                **output, timeout=timeout)
        if result.returncode:
            raise RuntimeError("Owned stack command failed; details withheld")
        return result.stdout

    def compose(self, *arguments):
        if not re.fullmatch(r"dpr-repro-[0-9a-f]{16}", self.project):
            raise ValueError("Invalid owned project")
        return self.command(["docker", "compose", "-p", self.project, "-f",
                             str(ROOT / "infra/reproduce/compose.yaml"), *arguments])

    def parameters(self, database="postgres", role="dpr_bootstrap", password=None):
        values = {"host": "127.0.0.1", "port": self.pg_port, "dbname": database, "user": role,
                  "password": password or self.password, "sslmode": "verify-full",
                  "sslrootcert": str(self.root / "postgres/tls/ca.crt"), "gssencmode": "disable", "connect_timeout": 5}
        return values

    def connection(self, database="postgres", role="dpr_bootstrap", password=None, **kwargs):
        import psycopg
        values = self.parameters(database, role, password)
        values.pop("native_bin", None)
        return psycopg.connect(**values, **kwargs)

    def pg_environment(self):
        return {**self.child_env, "PGHOST": "127.0.0.1", "PGPORT": str(self.pg_port),
                "PGPASSWORD": self.password, "PGSSLMODE": "verify-full",
                "PGSSLROOTCERT": str(self.root / "postgres/tls/ca.crt"), "PGGSSENCMODE": "disable"}

    def __enter__(self):
        try:
            make_ca(self.root / "tls")
            make_certificate(self.root)
            write_private(self.root / "postgres-password", (self.password + "\n").encode())
            if self.pg_bin:
                self.start_native()
            else:
                self.start_docker()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def start_native(self):
        if b" 18." not in self.command([self.executable("postgres"), "--version"]):
            raise ValueError("PostgreSQL 18 required")
        if b"v2.5.5" not in self.command([str(self.bao_bin), "version"]):
            raise ValueError("OpenBao 2.5.5 required")
        self.command([self.executable("initdb"), "-D", str(self.root / "pgdata"), "-U", "dpr_bootstrap",
                      "--encoding=UTF8", "--locale=C", "--auth-host=scram-sha-256", "--auth-local=scram-sha-256",
                      "--pwfile=" + str(self.root / "postgres-password")])
        cert = (self.root / "postgres/tls/server.crt").as_posix().replace("'", "''")
        key = (self.root / "postgres/tls/server.key").as_posix().replace("'", "''")
        with (self.root / "pgdata/postgresql.conf").open("a", encoding="utf-8") as out:
            out.write(f"\nlisten_addresses='127.0.0.1'\nport={self.pg_port}\nssl=on\nssl_cert_file='{cert}'\nssl_key_file='{key}'\n"
                      "ssl_min_protocol_version='TLSv1.2'\nlog_statement='none'\nlog_min_error_statement='panic'\n"
                      "log_parameter_max_length=0\nlog_parameter_max_length_on_error=0\n")
        (self.root / "pgdata/pg_hba.conf").write_text(
            "hostssl all all 127.0.0.1/32 scram-sha-256\nhostnossl all all 127.0.0.1/32 reject\n"
            "hostssl all all ::1/128 scram-sha-256\nhostnossl all all ::1/128 reject\n", encoding="utf-8")
        self.pg_started = True
        # The postmaster inherits pipe handles on Windows: capturing its stdout
        # can wait forever even after pg_ctl exits. Server log is private instead.
        self.command([self.executable("pg_ctl"), "-D", str(self.root / "pgdata"), "-l", str(self.root / "postgres.log"), "-w", "start"], quiet=True)
        address = f"https://127.0.0.1:{self.bao_port}"
        configuration = {"disable_mlock": True, "ui": False, "api_addr": address,
                         "storage": {"file": {"path": str(self.root / "bao-storage")}},
                         "listener": {"tcp": {"address": f"127.0.0.1:{self.bao_port}", "tls_min_version": "tls12",
                                               "tls_cert_file": str(self.root / "tls/server.crt"),
                                               "tls_key_file": str(self.root / "tls/server.key")}}}
        write_private(self.root / "bao.json", json.dumps(configuration).encode())
        flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        self.bao_process = subprocess.Popen([str(self.bao_bin), "server", "-config=" + str(self.root / "bao.json")],
                                            env=self.child_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **flags)

    def start_docker(self):
        from infra.postgres.enable_tls import ExistingPostgres, TLSUpdateError
        self.command(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=30)
        self.compose_started = True
        self.compose("up", "-d")
        self.pg_port = int(self.compose("port", "postgres", "5432").decode().strip().rsplit(":", 1)[1])
        self.bao_port = int(self.compose("port", "openbao", "8200").decode().strip().rsplit(":", 1)[1])
        for _ in range(90):
            try:
                pg = ExistingPostgres(self.container, port=self.pg_port)
                if pg.info["Config"]["Labels"].get("dpr.scope") != "submission-reproduction":
                    raise ValueError("Unexpected container ownership")
                pg.metadata()
                break
            except TLSUpdateError:
                time.sleep(1)
        else:
            raise RuntimeError("Fresh PostgreSQL startup timeout")
        pg.apply(self.root, baseline_address="disabled")

    def __exit__(self, *_):
        errors = []
        if self.bao_process and self.bao_process.poll() is None:
            self.bao_process.terminate()
            try:
                self.bao_process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.bao_process.kill()
                self.bao_process.wait(timeout=10)
        if self.pg_started:
            try:
                self.command([self.executable("pg_ctl"), "-D", str(self.root / "pgdata"), "-m", "fast", "-w", "stop"])
                self.pg_started = False
            except Exception:
                errors.append("owned_pg_stop_failed")
        if self.compose_started:
            try:
                # This invocation's random project only; never global prune/down.
                self.compose("down", "--volumes", "--remove-orphans")
                self.compose_started = False
            except Exception:
                errors.append("owned_compose_cleanup_failed")
        if errors:
            raise RuntimeError("Owned stack cleanup failed; inspect private reproduction directory")
