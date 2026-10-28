"""Enable TLS on an EXISTING PG18 container with ALTER SYSTEM + reload, no restart."""

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import ipaddress
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
from infra.protected.credentials import role_password


SSL_SETTINGS = ("ssl", "ssl_cert_file", "ssl_key_file", "ssl_min_protocol_version")
DATABASES = ("baseline_100k", "protected_734", "protected_100k", "baseline_1m", "protected_1m")
BASELINES = ("baseline_100k", "baseline_1m")
BASELINE_ROLES = ("bench_user", "scanner_user")
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


def baseline_hba_block(address: str) -> str:
    # The address observed by PostgreSQL, not a guessed Docker subnet or /0.
    client = ipaddress.ip_address(address)
    if "%" in address or client.is_unspecified or client.is_multicast:
        raise ValueError("An exact unicast client address is required")
    # Only non-TLS authentication is excepted. Existing hostssl/cert rules retain
    # their precedence and authentication method for encrypted connections.
    exception = f"hostnossl {','.join(BASELINES)} {','.join(BASELINE_ROLES)} {client}/{client.max_prefixlen} scram-sha-256\n"
    return HBA_BLOCK.replace("# BEGIN DPR PROJECT TLS\n", "# BEGIN DPR PROJECT TLS\n" + exception, 1)


def split_managed_hba(original: bytes) -> tuple[bytes, str | None]:
    """Recognize only our exact strict blocks or a validated exact-IP exception."""
    content = original.decode("utf-8")
    begin, end = "# BEGIN DPR PROJECT TLS\n", "# END DPR PROJECT TLS\n"
    address = None
    if content.startswith(begin) and end in content:
        stop = content.index(end)+len(end)
        block, suffix = content[:stop], content[stop:]
        if block not in (HBA_BLOCK, LEGACY_HBA_BLOCK):
            match = re.fullmatch(r"host(?:nossl)? baseline_100k,baseline_1m bench_user,scanner_user ([^\s/]+)/(32|128) scram-sha-256", block.splitlines()[1])
            try:
                if not match: raise ValueError()
                candidate = baseline_hba_block(match[1])
                legacy = candidate.replace("hostnossl baseline_", "host baseline_", 1)
                if block not in (candidate, legacy): raise ValueError()
                address = str(ipaddress.ip_address(match[1]))
            except ValueError:
                raise TLSUpdateError("unexpected_managed_hba_block") from None
    else:
        suffix = content
    if "# BEGIN DPR PROJECT TLS" in suffix or "# END DPR PROJECT TLS" in suffix:
        raise TLSUpdateError("unexpected_managed_hba_block")
    return suffix.encode("utf-8"), address


def managed_hba(original: bytes, baseline_address: str | None = None) -> bytes:
    suffix, _ = split_managed_hba(original)
    desired = baseline_hba_block(baseline_address) if baseline_address else HBA_BLOCK
    return desired.encode()+suffix


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


def plaintext_rejected(host: str, port: int, database: str, user: str = "dpr_tls_probe") -> bool:
    try:
        # A synthetic password proves HBA rejection before password authentication.
        with psycopg.connect(host=host, port=port, dbname=database, user=user,
                password=secrets.token_urlsafe(24), sslmode="disable", gssencmode="disable", connect_timeout=3):
            return False
    except psycopg.OperationalError as error:
        # libpq startup failures do not always expose diag.sqlstate. Do not log text.
        return "pg_hba.conf rejects connection" in str(error) and "no encryption" in str(error)


def baseline_passwords(root: Path) -> dict:
    password = os.environ.get("DPR_BENCH_USER_PASSWORD")
    if not password:
        raise TLSUpdateError("baseline_bench_credential_required")
    # This verifies an existing login, not the strength of a newly created password.
    scanner = os.environ.get("DPR_SCANNER_USER_PASSWORD") or role_password(root, "scanner_user")
    return {"bench_user": password, "scanner_user": scanner}


def optional_role_password(root: Path, role: str) -> str | None:
    value = os.environ.get("DPR_"+role.upper()+"_PASSWORD")
    if value: return value
    if (root/"postgres/roles"/(role+".credential.xml")).is_file():
        return role_password(root, role)
    return None


def connection_matrix(root: Path, host: str, port: int, existing_databases: dict,
                      baseline_address: str | None = None) -> dict:
    checks = {}
    credentials = baseline_passwords(root) if baseline_address else {}
    app_password = optional_role_password(root, "app_user")
    for role, password in credentials.items():
        for database in BASELINES:
            if database not in existing_databases: continue
            try:
                with psycopg.connect(host=host, port=port, dbname=database, user=role, password=password,
                        sslmode="disable", gssencmode="disable", connect_timeout=5,
                        options="-c default_transaction_read_only=on") as connection:
                    actual = connection.execute("SELECT current_user,current_database(),ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()").fetchone()
                allowed = actual == (role, database, False)
            except psycopg.Error:
                allowed = False
            checks[f"baseline_plaintext_allowed:{database}:{role}"] = allowed
    for database in DATABASES:
        checks["plaintext_rejected:" + database] = plaintext_rejected(host, port, database)
        denied = ("app_user", "postgres", "migration_user", "analyst_user", "auditor_user", "backup_user", "admin_user", "schema_owner")
        if database not in BASELINES or not baseline_address: denied += BASELINE_ROLES
        for role in denied:
            checks[f"plaintext_rejected:{database}:{role}"] = plaintext_rejected(host, port, database, role)
        if database not in BASELINES and database in existing_databases and app_password:
            try:
                with psycopg.connect(host=host, port=port, dbname=database, user="app_user",
                        password=app_password, sslmode="verify-full",
                        sslrootcert=str(root / "postgres/tls/ca.crt"), gssencmode="disable", connect_timeout=5,
                        options="-c default_transaction_read_only=on") as connection:
                    actual = connection.execute("SELECT current_user,current_database(),ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()").fetchone()
                verified = actual == ("app_user", database, True)
            except psycopg.Error:
                verified = False
            checks["protected_verify_full:" + database] = verified
    return checks


def matrix_coverage(existing_databases: dict, checks: dict, baseline_address: str | None) -> dict:
    protected = [db for db in DATABASES if db not in BASELINES and "protected_verify_full:"+db not in checks]
    baselines = [db for db in BASELINES if db not in existing_databases] if baseline_address else []
    return {"baseline_databases_pending": baselines, "protected_databases_pending_prepare": protected,
            "connection_matrix_complete": not protected and not baselines}


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

    def read_hba(self) -> bytes:
        # The administrative connection stays inside the selected container.
        return base64.b64decode(self.query("SELECT encode(pg_read_binary_file(current_setting('hba_file')),'base64');"))

    def apply(self, root: Path, *, baseline_address: str | None = None) -> tuple[Path, dict]:
        root = external_directory(str(root))
        before = self.metadata()
        material = root / "postgres/tls"
        for name in ("server.crt", "server.key", "ca.crt"):
            if not (material / name).is_file():
                raise TLSUpdateError("postgresql_certificate_material_missing")
        original_hba = self.read_hba()
        _, previous_address = split_managed_hba(original_hba)
        # Preserve an installed benchmark exception by default, but do not add
        # one or require benchmark credentials on a fresh/strict installation.
        selected = previous_address if baseline_address is None else baseline_address
        if selected == "disabled": selected = None
        if selected is not None and selected != "auto":
            baseline_hba_block(selected)  # Validate before any mutation.
            selected = str(ipaddress.ip_address(selected))
        credentials = baseline_passwords(root) if selected else {}
        discovery_database = next((db for db in BASELINES if db in before["database_oids"]), None)
        if selected == "auto" and not discovery_database:
            raise TLSUpdateError("baseline_database_required_for_discovery")
        snapshot = secure_directory(root / "postgres" / "changes" / uuid.uuid4().hex)
        state_path = snapshot / "state.json"
        hba = snapshot / "pg_hba.before.conf"
        self.run(["cp", self.container + ":" + before["hba_file"], str(hba)])
        self.run(["cp", self.container + ":" + before["data_directory"] + "/postgresql.auto.conf", str(snapshot / "postgresql.auto.before.conf")])
        if hba.read_bytes() != original_hba:
            raise TLSUpdateError("hba_changed_before_snapshot")
        staged_hba = snapshot / "pg_hba.after.conf"
        certificate_dir = before["data_directory"] + "/dpr-tls/" + uuid.uuid4().hex
        desired = {"ssl": "on", "ssl_cert_file": certificate_dir + "/server.crt",
                   "ssl_key_file": certificate_dir + "/server.key", "ssl_min_protocol_version": "TLSv1.2"}
        state = {"container_id": self.info["Id"], "before": before, "desired": desired, "status": "prepared",
                 "hba_before_sha256": hashlib.sha256(hba.read_bytes()).hexdigest(),
                 "hba_applied_sha256": hashlib.sha256(original_hba).hexdigest()}
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
            if selected == "auto":
                # Enable/verify TLS first: even an old hostnossl reject block on
                # an ssl=off installation must be upgradeable without sending
                # real discovery credentials over plaintext.
                try:
                    with psycopg.connect(host=self.host, port=self.port, dbname=discovery_database,
                            user="bench_user", password=credentials["bench_user"], sslmode="verify-full",
                            sslrootcert=str(material/"ca.crt"), gssencmode="disable", connect_timeout=5,
                            options="-c default_transaction_read_only=on") as connection:
                        selected = connection.execute("SELECT host(inet_client_addr())").fetchone()[0]
                except psycopg.Error:
                    raise TLSUpdateError("baseline_client_address_discovery_failed") from None
                baseline_hba_block(selected)
                selected = str(ipaddress.ip_address(selected))
            modified = managed_hba(original_hba, selected)
            write_private(staged_hba, modified)
            state["hba_applied_sha256"] = hashlib.sha256(modified).hexdigest()
            save_state(state_path, state)
            # Enforce only after a verified TLS connection has succeeded.
            self.install_file(staged_hba, before["hba_file"], "600")
            if self.query("SELECT count(*) FROM pg_hba_file_rules WHERE error IS NOT NULL;") != "0":
                raise TLSUpdateError("hba_parse_error")
            after = self.reload(desired)
            access = connection_matrix(root, self.host, self.port, after["database_oids"], selected)
            current_info = json.loads(self.run(["inspect", self.container]))[0]
            checks = {"tls_on": after["settings"]["ssl"] == "on", "hostname_verified": tls["hostname_verified"],
                      "same_container": current_info["Id"] == self.info["Id"],
                      "no_postmaster_restart": before["started_at"] == after["started_at"],
                      "database_oids_unchanged": before["database_oids"] == after["database_oids"],
                      **access}
            if not all(checks.values()):
                raise TLSUpdateError("post_apply_verification_failed")
            state["status"] = "applied"
            save_state(state_path, state)
            return state_path, {"passed": True, "checks": checks, **tls, "server_version_num": after["version"],
                "baseline_client_address": selected, **matrix_coverage(after["database_oids"], checks, selected)}
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
    parser.add_argument("--baseline-client-address", default=os.environ.get("DPR_BASELINE_CLIENT_ADDRESS"),
        help="Benchmark exception: auto, an exact IPv4/IPv6 address, or disabled. Default preserves existing policy.")
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
                state_path, result = target.apply(root, baseline_address=args.baseline_client_address)
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
                _, active_address = split_managed_hba(target.read_hba())
                checks = {"tls_on": metadata["settings"]["ssl"] == "on",
                          **connection_matrix(root, args.host, args.port, metadata["database_oids"], active_address)}
                requested = args.baseline_client_address
                if requested is not None:
                    expected = None if requested == "disabled" else active_address if requested == "auto" else str(ipaddress.ip_address(requested))
                    checks["configured_baseline_address_matches"] = active_address == expected and (requested != "auto" or active_address is not None)
                report.update(passed=all(checks.values()), checks=checks, baseline_client_address=active_address,
                    **matrix_coverage(metadata["database_oids"], checks, active_address), **tls)
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
