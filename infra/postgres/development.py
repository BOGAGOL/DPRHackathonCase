"""Create a LOCAL development clone; official benchmark evidence is never overwritten."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import time

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from datagen.model import COLUMNS, checksum
from infra.postgres.credentials import load_password, save_password
from infra.postgres.enable_tls import ExistingPostgres, TLSUpdateError
from infra.security import REPO, external_directory, secure_directory
from scanner.sources import InputError, SQLStream, split_items


def docker(args: list[str], *, environment=None) -> str:
    result = subprocess.run(["docker", *args], env=environment, capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise RuntimeError("Local Docker operation failed; output withheld")
    return result.stdout.strip()


def create_container(root: Path) -> dict:
    if os.environ.get("DPR_DOCKER_CONTEXT") or os.environ.get("DOCKER_HOST"):
        raise RuntimeError("Local development bootstrap requires the local Docker context")
    endpoint = json.loads(docker(["context", "inspect", "--format", "{{json .Endpoints.docker.Host}}"]))
    if not isinstance(endpoint, str) or not endpoint.startswith(("npipe://", "unix://")):
        raise RuntimeError("Local development bootstrap requires the local Docker context")
    docker(["info", "--format", "{{.ServerVersion}}"])
    existing = subprocess.run(["docker", "inspect", "pg-dpr"], capture_output=True, text=True)
    if existing.returncode == 0:
        raise RuntimeError("pg-dpr exists; refusing to recreate or change its credentials")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 5433))
    volume = subprocess.run(["docker", "volume", "inspect", "pg-dpr-data"], capture_output=True, text=True)
    if volume.returncode == 0:
        info = json.loads(volume.stdout)[0]
        if (info.get("Labels") or {}).get("dpr.scope") != "development":
            raise RuntimeError("Existing pg-dpr-data volume requires operator review; no replacement")
        # Resume an interrupted empty-volume setup only; never initialize over data.
        docker(["run", "--rm", "--entrypoint", "sh", "--mount",
                "type=volume,source=pg-dpr-data,target=/check,readonly", "postgres:18", "-ceu", 'test -z "$(ls -A /check)"'])
    else:
        docker(["volume", "create", "--label", "dpr.scope=development", "pg-dpr-data"])
    if (root / "postgres/admin.credential.xml").exists():
        password = load_password(root)
    else:
        password = os.environ.get("POSTGRES_PASSWORD") or secrets.token_urlsafe(36)
        save_password(root, password)
    docker(["run", "-d", "--name", "pg-dpr", "--label", "dpr.scope=development", "--restart", "unless-stopped",
            "--env", "POSTGRES_PASSWORD", "--env", "POSTGRES_USER=postgres",
            "--env", "POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256",
            "--publish", "127.0.0.1:5433:5432", "--mount", "type=volume,source=pg-dpr-data,target=/var/lib/postgresql",
            "postgres:18"], environment={**os.environ, "POSTGRES_PASSWORD": password})
    target = ExistingPostgres()
    for _ in range(60):
        try:
            state = target.metadata()
            return {"container": "pg-dpr", "port": 5433, "server_version_num": state["version"], "persistent_volume": "pg-dpr-data"}
        except TLSUpdateError:
            time.sleep(0.5)
    raise RuntimeError("New development PostgreSQL did not become ready")


def read_source(path: Path, expected_rows: int = 734) -> list[dict]:
    """Parse literal INSERTs without executing the source SQL or creating plaintext temps."""
    columns = list(COLUMNS[1:])
    rows = []
    with path.open(encoding="utf-8-sig") as handle:
        stream = SQLStream(handle)
        while (token := stream.token()) is not None:
            if token == ("punct", ";"):
                continue
            if token[0] != "word":
                raise ValueError("Unsupported source SQL")
            command = token[1].upper()
            if command in ("BEGIN", "COMMIT"):
                stream.expect(";")
                continue
            if command != "INSERT":
                raise ValueError("Source must contain only literal anggota INSERTs")
            stream.expect("INTO")
            if stream.identifier() not in ("anggota", "public.anggota"):
                raise ValueError("Unexpected source table")
            items = split_items(stream)
            if any(len(item) != 1 for item in items) or [item[0][1] for item in items] != columns:
                raise ValueError("Source columns do not match the agreed schema")
            stream.expect("VALUES")
            items = split_items(stream)
            values = []
            for item in items:
                if len(item) != 1 or item[0][0] not in ("value", "word"):
                    raise ValueError("Only source literals are allowed")
                kind, value = item[0]
                if kind == "word" and value.upper() != "NULL" and not re.fullmatch(r"[+-]?[0-9]+", value):
                    raise ValueError("Only source literals are allowed")
                values.append(None if kind == "word" and value.upper() == "NULL" else value)
            if len(values) != len(columns):
                raise ValueError("Source field count mismatch")
            rows.append(dict(zip(columns, values)))
            stream.expect(";")
    if len(rows) != expected_rows:
        raise ValueError("Source row count mismatch")
    return rows


def parameters(root: Path, database: str) -> dict:
    return {"host": "127.0.0.1", "port": 5433, "user": "postgres", "password": load_password(root),
            "dbname": database, "sslmode": "verify-full", "sslrootcert": str(root / "postgres/tls/ca.crt"),
            "gssencmode": "disable", "connect_timeout": 5}


def validate_source(root: Path) -> dict:
    with psycopg.connect(**parameters(root, "postgres")) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        result = connection.execute("""SELECT count(*), count(DISTINCT no_ktp), min(length(no_ktp)), max(length(no_ktp)),
            count(*) FILTER (WHERE status_kawin='K'), count(tanggal_pernikahan) FROM public.anggota""").fetchone()
        actual = {"rows": result[0], "ktp_unique": result[1], "nik_min_length": result[2], "nik_max_length": result[3],
                  "married": result[4], "marriage_dates": result[5]}
        actual["passed"] = tuple(result) == (734, 734, 14, 14, 367, 367)
        return actual


def import_source(root: Path, path: Path) -> dict:
    rows = read_source(path)
    with psycopg.connect(**parameters(root, "postgres")) as connection:
        # Initial population of a NEW local clone only. Never overwrite existing source.
        if connection.execute("SELECT to_regclass(%s)", ("public.anggota",)).fetchone()[0] is not None:
            raise RuntimeError("Source table exists; refusing to overwrite it")
        schema = (REPO / "sql/baseline/01_schema.sql").read_text(encoding="utf-8-sig")
        connection.execute(schema)
        insert = sql.SQL("INSERT INTO public.anggota ({}) VALUES ({})").format(
            sql.SQL(",").join(map(sql.Identifier, COLUMNS[1:])), sql.SQL(",").join(sql.Placeholder() for _ in COLUMNS[1:]))
        with connection.cursor() as cursor:
            cursor.executemany(insert, [tuple(row[column] for column in COLUMNS[1:]) for row in rows])
        connection.execute("ANALYZE public.anggota")
    result = validate_source(root)
    result["input_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not result["passed"]:
        raise RuntimeError("Imported local source failed aggregate validation")
    return result


def generate_baseline(root: Path) -> dict:
    # Reuse C's complete generator/validation/provenance; route ONLY its evidence sink
    # to development/ so the official laptop's baseline/benchmark report is untouched.
    from datagen import database
    official = REPO / "evidence/datasets/baseline_100k.json"
    official_hash = hashlib.sha256(official.read_bytes()).hexdigest()
    expected = json.loads(official.read_text(encoding="utf-8"))["baseline_checksum_sha256"]
    original_record = database.record
    previous_env = os.environ.get("DATAGEN_DATABASE_URL")
    def development_record(name, payload):
        output = REPO / "evidence/development" / (name + ".json")
        output.parent.mkdir(parents=True, exist_ok=True)
        result = {**payload, "scope": "local development clone; not official benchmark", "official_benchmark": False}
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    try:
        os.environ["DATAGEN_DATABASE_URL"] = make_conninfo(**parameters(root, "postgres"))
        database.record = development_record
        result = database.build("baseline_100k", 100000, 42, True)
        matches = result["baseline_checksum_sha256"] == expected
        if not matches or hashlib.sha256(official.read_bytes()).hexdigest() != official_hash:
            raise RuntimeError("Development clone differs or official evidence changed")
        return {"rows": 100000, "seed": 42, "matches_official_checksum": matches, "official_evidence_unchanged": True,
                "baseline_checksum_sha256": result["baseline_checksum_sha256"]}
    finally:
        database.record = original_record
        if previous_env is None:
            os.environ.pop("DATAGEN_DATABASE_URL", None)
        else:
            os.environ["DATAGEN_DATABASE_URL"] = previous_env


def create_empty_targets(root: Path) -> list[str]:
    created = []
    with psycopg.connect(**parameters(root, "template1"), autocommit=True) as connection:
        for name in ("protected_734", "protected_100k"):
            if not connection.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone():
                connection.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0 ENCODING 'UTF8'").format(sql.Identifier(name)))
                created.append(name)
    return created


def verify_development(root: Path) -> dict:
    from psycopg.rows import dict_row
    official = json.loads((REPO / "evidence/datasets/baseline_100k.json").read_text(encoding="utf-8"))
    expected = {"postgres": official["validation"]["source_checksum_sha256"],
                "baseline_100k": official["baseline_checksum_sha256"]}
    checks, databases = {}, {}
    for name in ("postgres", "baseline_100k", "protected_734", "protected_100k"):
        with psycopg.connect(**parameters(root, name), row_factory=dict_row) as connection:
            connection.execute("SET TRANSACTION READ ONLY")
            tls = connection.execute("SELECT ssl, version FROM pg_stat_ssl WHERE pid=pg_backend_pid()").fetchone()
            checks["verified_tls:" + name] = bool(tls["ssl"]) and tls["version"] in ("TLSv1.2", "TLSv1.3")
            databases[name] = {"tls": tls["version"]}
            if name in expected:
                count = connection.execute("SELECT count(*) AS rows FROM public.anggota").fetchone()["rows"]
                with connection.cursor(name="development_checksum") as cursor:
                    cursor.execute(sql.SQL("SELECT {} FROM public.anggota ORDER BY id").format(sql.SQL(",").join(map(sql.Identifier, COLUMNS))))
                    actual = checksum(cursor)
                checks["rows:" + name] = count == (734 if name == "postgres" else 100000)
                checks["official_checksum:" + name] = actual == expected[name]
                databases[name].update(rows=count, checksum_sha256=actual)
            else:
                databases[name]["public_tables"] = connection.execute(
                    "SELECT count(*) AS tables FROM pg_tables WHERE schemaname=%s", ("public",)).fetchone()["tables"]
    return {"passed": all(checks.values()), "checks": checks, "databases": databases}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("create", "import-source", "validate-source", "baseline", "empty-targets", "verify"))
    parser.add_argument("--data-file", type=Path, default=REPO / "sql/baseline/02_data.sql")
    args = parser.parse_args()
    report = {"schema_version": 1, "command": args.command, "passed": False, "official_benchmark": False,
              "scope": "local development only", "checked_at_utc": datetime.now(timezone.utc).isoformat()}
    try:
        root = secure_directory(external_directory(os.environ.get("DPR_SECRETS_DIR")))
        if args.command == "create":
            result = create_container(root)
        elif args.command == "import-source":
            result = import_source(root, args.data_file)
        elif args.command == "validate-source":
            result = validate_source(root)
        elif args.command == "baseline":
            result = generate_baseline(root)
        elif args.command == "verify":
            result = verify_development(root)
        else:
            result = {"new_empty_databases": create_empty_targets(root)}
        report.update(result=result, passed=result.get("passed", True))
    except (Exception, InputError):
        report["error"] = "development_setup_failed_details_withheld"
    output = REPO / "evidence/development" / (args.command + ".json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Development PostgreSQL " + args.command + ": " + ("PASS" if report["passed"] else "FAIL"))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
