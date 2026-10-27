"""Enable TLS on an EXISTING PG18 container with ALTER SYSTEM + reload, no restart."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import socket
import ssl
import struct
import subprocess
import time
import uuid

from cryptography import x509
from cryptography.hazmat.primitives import hashes
import psycopg
from psycopg import sql

from infra.security import REPO, external_directory, secure_directory, write_private


SSL_SETTINGS = ("ssl", "ssl_cert_file", "ssl_key_file", "ssl_min_protocol_version")
DATABASES = ("baseline_100k", "protected_734", "protected_100k", "baseline_1m", "protected_1m")
LEGACY_HBA_BLOCK = ("# BEGIN DPR PROJECT TLS\n"
             "hostnossl baseline_100k,protected_734,protected_100k all 0.0.0.0/0 reject\n"
             "hostnossl baseline_100k,protected_734,protected_100k all ::/0 reject\n"
             "# END DPR PROJECT TLS\n")
HBA_BLOCK = ("# BEGIN DPR PROJECT TLS\n"
             f"hostnossl {','.join(DATABASES)} all 0.0.0.0/0 reject\n"
             f"hostnossl {','.join(DATABASES)} all ::/0 reject\n"
             "# END DPR PROJECT TLS\n")


class TLSUpdateError(RuntimeError):
    """Only a fixed non-secret failure code may be reported."""


def managed_hba(original: bytes) -> bytes:
    content = original.decode("utf-8")
    for block in (HBA_BLOCK,LEGACY_HBA_BLOCK):
        if content.startswith(block):
            suffix=content[len(block):]
            if "# BEGIN DPR PROJECT TLS" in suffix or "# END DPR PROJECT TLS" in suffix:
                raise TLSUpdateError("unexpected_managed_hba_block")
            return HBA_BLOCK.encode()+suffix.encode("utf-8")
    if "# BEGIN DPR PROJECT TLS" in content or "# END DPR PROJECT TLS" in content:
        raise TLSUpdateError("unexpected_managed_hba_block")
    return HBA_BLOCK.encode() + original


def save_state(path: Path, state: dict) -> None:
    pending = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    write_private(pending, (json.dumps(state, indent=2) + "\n").encode())
    pending.replace(path)


def verify_tls(host: str, port: int, ca: Path, expected_certificate: Path) -> dict:
    context = ssl.create_default_context(cafile=str(ca))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        with socket.create_connection((host, port), timeout=5) as raw:
            raw.sendall(struct.pack("!II", 8, 80877103))
            if raw.recv(1) != b"S":
                raise TLSUpdateError("server_did_not_offer_tls")
            with context.wrap_socket(raw, server_hostname=host) as channel:
                actual = hashlib.sha256(channel.getpeercert(binary_form=True)).hexdigest()
                expected = x509.load_pem_x509_certificate(expected_certificate.read_bytes()).fingerprint(hashes.SHA256()).hex()
                if actual != expected:
                    raise TLSUpdateError("unexpected_server_certificate")
                return {"tls_version": channel.version(), "certificate_sha256": actual, "hostname_verified": True}
    except (OSError, ValueError):
        raise TLSUpdateError("verified_tls_connection_failed") from None


def plaintext_rejected(host: str, port: int, database: str) -> bool:
    try:
        # Synthetic nonexistent user/password: never send a real credential without TLS.
        with psycopg.connect(host=host, port=port, dbname=database, user="dpr_tls_probe",
                password=secrets.token_urlsafe(24), sslmode="disable", gssencmode="disable", connect_timeout=3):
            return False
    except psycopg.OperationalError as error:
        # libpq startup failures do not always expose diag.sqlstate. Do not log text.
        return "pg_hba.conf rejects connection" in str(error) and "no encryption" in str(error)


class ExistingPostgres:
    def __init__(self, container: str = "pg-dpr", *, host: str = "127.0.0.1", port: int = 5433):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", container) or not 1 <= port <= 65535:
            raise TLSUpdateError("invalid_existing_container_endpoint")
        self.container, self.host, self.port = container, host, port
        self.docker = ["docker"]
        if os.environ.get("DPR_DOCKER_CONTEXT"):
            self.docker += ["--context", os.environ["DPR_DOCKER_CONTEXT"]]
        self.info = json.loads(self.run(["inspect", container]))[0]
        if not self.info["State"]["Running"]:
            raise TLSUpdateError("existing_container_not_running")
        bindings = self.info["NetworkSettings"]["Ports"].get("5432/tcp") or []
        if not any(item["HostPort"] == str(port) for item in bindings):
            raise TLSUpdateError("published_port_mismatch")
        environment = dict(item.split("=", 1) for item in self.info["Config"].get("Env", []) if "=" in item)
        self.admin = os.environ.get("DPR_POSTGRES_ADMIN_USER") or environment.get("POSTGRES_USER", "postgres")

    def run(self, args: list[str], *, stdin: str | None = None) -> str:
        try:
            result = subprocess.run(self.docker + args, input=stdin, capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise TLSUpdateError("docker_or_postgresql_operation_failed")
            return result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            raise TLSUpdateError("docker_unavailable_or_timed_out") from None

    def query(self, statement: str) -> str:
        # Unix socket admin access; never connect to or modify the original postgres DB.
        return self.run(["exec", "-i", "--user", "postgres", self.container, "psql", "-X", "-w",
                         "-v", "ON_ERROR_STOP=1", "-A", "-t", "-q", "-U", self.admin, "-d", "template1"], stdin=statement + "\n")

    def metadata(self) -> dict:
        # The image's temporary initdb postmaster accepts Unix sockets before it
        # shuts down. Require the final TCP listener before changing settings.
        self.run(["exec", "--user", "postgres", self.container, "pg_isready", "-h", "127.0.0.1",
                  "-p", "5432", "-U", self.admin, "-d", "template1"])
        # Only cluster configuration/catalog metadata, no source table contents.
        result = json.loads(self.query("""
SELECT json_build_object(
 'version', current_setting('server_version_num')::int,
 'data_directory', current_setting('data_directory'), 'hba_file', current_setting('hba_file'),
 'started_at', pg_postmaster_start_time(),
 'superuser', (SELECT rolsuper FROM pg_roles WHERE rolname = current_user),
 'settings', (SELECT json_object_agg(name, setting) FROM pg_settings WHERE name IN
   ('ssl','ssl_cert_file','ssl_key_file','ssl_min_protocol_version')),
 'contexts', (SELECT json_object_agg(name, context) FROM pg_settings WHERE name IN
   ('ssl','ssl_cert_file','ssl_key_file','ssl_min_protocol_version')),
 'overrides', coalesce((SELECT json_object_agg(name, setting ORDER BY seqno) FROM pg_file_settings
   WHERE sourcefile = current_setting('data_directory') || '/postgresql.auto.conf'
   AND name IN ('ssl','ssl_cert_file','ssl_key_file','ssl_min_protocol_version')), '{}'::json),
 'command_line_override', EXISTS(SELECT 1 FROM pg_settings WHERE name IN
   ('ssl','ssl_cert_file','ssl_key_file','ssl_min_protocol_version') AND source = 'command line'),
 'database_oids', (SELECT json_object_agg(datname, oid) FROM pg_database
   WHERE datname IN ('postgres','baseline_100k','protected_734','protected_100k','baseline_1m','protected_1m')));
"""))
        if not result["superuser"] or not 180000 <= result["version"] < 190000:
            raise TLSUpdateError("requires_pg18_cluster_admin")
        if result["command_line_override"] or any(value != "sighup" for value in result["contexts"].values()):
            raise TLSUpdateError("ssl_settings_not_reloadable")
        data = PurePosixPath(result["data_directory"])
        hba = PurePosixPath(result["hba_file"])
        if (not data.is_absolute() or ".." in data.parts or ".." in hba.parts or not hba.is_relative_to(data)
                or not any(data.is_relative_to(PurePosixPath(mount["Destination"])) and mount.get("RW")
                           for mount in self.info["Mounts"] if mount["Type"] in ("volume", "bind"))):
            raise TLSUpdateError("configuration_not_in_persistent_data_mount")
        return result

    def alter(self, name: str, value: str | None) -> None:
        if name not in SSL_SETTINGS:
            raise TLSUpdateError("unexpected_configuration_parameter")
        statement = (sql.SQL("ALTER SYSTEM RESET {};").format(sql.Identifier(name)) if value is None else
                     sql.SQL("ALTER SYSTEM SET {} TO {};").format(sql.Identifier(name), sql.Literal(value)))
        # Each ALTER SYSTEM has its own psql autocommit command, never a transaction block.
        self.query(statement.as_string())

    def install_file(self, source: Path, target: str, mode: str) -> None:
        if mode not in ("600", "644") or not PurePosixPath(target).is_absolute() or ".." in PurePosixPath(target).parts:
            raise TLSUpdateError("invalid_install_target")
        pending = target + ".dpr-" + uuid.uuid4().hex + ".new"
        self.run(["cp", str(source), self.container + ":" + pending])
        # Only rename a known file within the persistent Linux data directory.
        self.run(["exec", "--user", "0", self.container, "sh", "-ceu",
                  'test ! -L "$1"; chown postgres:postgres "$2"; chmod "$3" "$2"; mv -f -- "$2" "$1"',
                  "sh", target, pending, mode])

    def reload(self, expected: dict) -> dict:
        self.query("SELECT pg_reload_conf();")
        for _ in range(30):
            metadata = self.metadata()
            if metadata["settings"] == expected:
                return metadata
            time.sleep(0.1)
        raise TLSUpdateError("ssl_reload_did_not_apply")

    def rollback(self, state_path: Path) -> None:
        state_path = external_directory(str(state_path))
        state = json.loads(state_path.read_text())
        if state["container_id"] != self.info["Id"]:
            raise TLSUpdateError("rollback_container_id_mismatch")
        current = self.metadata()
        if current["hba_file"] != state["before"]["hba_file"]:
            raise TLSUpdateError("hba_path_changed_since_snapshot")
        current_file = state_path.parent / ("hba-current-" + uuid.uuid4().hex + ".conf")
        self.run(["cp", self.container + ":" + current["hba_file"], str(current_file)])
        if hashlib.sha256(current_file.read_bytes()).hexdigest() not in (state["hba_before_sha256"], state["hba_applied_sha256"]):
            raise TLSUpdateError("hba_changed_since_snapshot")
        for name in SSL_SETTINGS:
            actual = current["overrides"].get(name)
            if actual not in (state["before"]["overrides"].get(name), state["desired"][name]):
                raise TLSUpdateError("ssl_changed_since_snapshot")
        original_hba = state_path.parent / "pg_hba.before.conf"
        if hashlib.sha256(original_hba.read_bytes()).hexdigest() != state["hba_before_sha256"]:
            raise TLSUpdateError("rollback_snapshot_integrity_failed")
        self.install_file(original_hba, current["hba_file"], "600")
        for name in SSL_SETTINGS:
            self.alter(name, state["before"]["overrides"].get(name))
        self.reload(state["before"]["settings"])
        state["status"] = "rolled_back"
        save_state(state_path, state)

    def apply(self, root: Path) -> tuple[Path, dict]:
        root = external_directory(str(root))
        before = self.metadata()
        material = root / "postgres/tls"
        for name in ("server.crt", "server.key", "ca.crt"):
            if not (material / name).is_file():
                raise TLSUpdateError("postgresql_certificate_material_missing")
        snapshot = secure_directory(root / "postgres" / "changes" / uuid.uuid4().hex)
        state_path = snapshot / "state.json"
        hba = snapshot / "pg_hba.before.conf"
        self.run(["cp", self.container + ":" + before["hba_file"], str(hba)])
        self.run(["cp", self.container + ":" + before["data_directory"] + "/postgresql.auto.conf", str(snapshot / "postgresql.auto.before.conf")])
        modified = managed_hba(hba.read_bytes())
        staged_hba = snapshot / "pg_hba.after.conf"
        write_private(staged_hba, modified)
        certificate_dir = before["data_directory"] + "/dpr-tls/" + uuid.uuid4().hex
        desired = {"ssl": "on", "ssl_cert_file": certificate_dir + "/server.crt",
                   "ssl_key_file": certificate_dir + "/server.key", "ssl_min_protocol_version": "TLSv1.2"}
        state = {"container_id": self.info["Id"], "before": before, "desired": desired, "status": "prepared",
                 "hba_before_sha256": hashlib.sha256(hba.read_bytes()).hexdigest(),
                 "hba_applied_sha256": hashlib.sha256(modified).hexdigest()}
        save_state(state_path, state)
        self.run(["exec", "--user", "0", self.container, "sh", "-ceu",
                  'test ! -L "$1/dpr-tls"; mkdir -p -- "$2"; chown postgres:postgres "$1/dpr-tls" "$2"; chmod 700 "$1/dpr-tls" "$2"',
                  "sh", before["data_directory"], certificate_dir])
        for name, mode in (("server.key", "600"), ("server.crt", "644"), ("ca.crt", "644")):
            self.install_file(material / name, certificate_dir + "/" + name, mode)
        try:
            for name, value in desired.items():
                self.alter(name, value)
            self.reload(desired)
            tls = verify_tls(self.host, self.port, material / "ca.crt", material / "server.crt")
            # Enforce only after a verified TLS connection has succeeded.
            self.install_file(staged_hba, before["hba_file"], "600")
            if self.query("SELECT count(*) FROM pg_hba_file_rules WHERE error IS NOT NULL;") != "0":
                raise TLSUpdateError("hba_parse_error")
            after = self.reload(desired)
            rejects = {database: plaintext_rejected(self.host, self.port, database) for database in DATABASES}
            current_info = json.loads(self.run(["inspect", self.container]))[0]
            checks = {"tls_on": after["settings"]["ssl"] == "on", "hostname_verified": tls["hostname_verified"],
                      "same_container": current_info["Id"] == self.info["Id"],
                      "no_postmaster_restart": before["started_at"] == after["started_at"],
                      "database_oids_unchanged": before["database_oids"] == after["database_oids"],
                      **{"plaintext_rejected:" + name: rejected for name, rejected in rejects.items()}}
            if not all(checks.values()):
                raise TLSUpdateError("post_apply_verification_failed")
            state["status"] = "applied"
            save_state(state_path, state)
            return state_path, {"passed": True, "checks": checks, **tls, "server_version_num": after["version"]}
        except Exception:
            self.rollback(state_path)
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inspect", "apply", "verify", "rollback"))
    parser.add_argument("--container", default=os.environ.get("DPR_POSTGRES_CONTAINER", "pg-dpr"))
    parser.add_argument("--host", default=os.environ.get("PGHOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PGPORT", "5433")))
    parser.add_argument("--state", type=Path)
    args = parser.parse_args()
    report = {"schema_version": 1, "passed": False, "command": args.command, "container": args.container,
              "host": args.host, "port": args.port, "checked_at_utc": datetime.now(timezone.utc).isoformat()}
    try:
        target = ExistingPostgres(args.container, host=args.host, port=args.port)
        if args.command == "inspect":
            metadata = target.metadata()
            report.update(passed=True, server_version_num=metadata["version"], ssl=metadata["settings"]["ssl"], databases=sorted(metadata["database_oids"]))
        else:
            root = secure_directory(external_directory(os.environ.get("DPR_SECRETS_DIR")))
            if args.command == "apply":
                state_path, result = target.apply(root)
                report.update(result, rollback_state_id=state_path.parent.name)
            elif args.command == "rollback":
                if args.state is None or not args.state.resolve().is_relative_to((root / "postgres/changes").resolve()):
                    raise TLSUpdateError("expected_external_rollback_state")
                target.rollback(args.state)
                report["passed"] = True
            else:
                material = root / "postgres/tls"
                metadata = target.metadata()
                tls = verify_tls(args.host, args.port, material / "ca.crt", material / "server.crt")
                checks = {"tls_on": metadata["settings"]["ssl"] == "on", **{
                    "plaintext_rejected:" + name: plaintext_rejected(args.host, args.port, name) for name in DATABASES}}
                report.update(passed=all(checks.values()), checks=checks, **tls)
    except (TLSUpdateError, ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
        report["error"] = str(error) if isinstance(error, TLSUpdateError) else "operation_failed_details_withheld"
    evidence = REPO / "evidence/infra/postgres-tls.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PostgreSQL TLS " + args.command + ": " + ("PASS" if report["passed"] else "FAIL") + "; evidence/infra/postgres-tls.json")
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
