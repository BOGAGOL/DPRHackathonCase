"""Encrypted logical backup and restore drill into a new lab database only."""
import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from dotenv import load_dotenv
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
MAGIC = b"DPRBACKUP1\x00"


def encrypt_dump(data: bytes, key: bytes) -> bytes:
    nonce = os.urandom(12)
    return MAGIC + nonce + AESGCM(key).encrypt(nonce, data, MAGIC)


def decrypt_dump(data: bytes, key: bytes) -> bytes:
    if not data.startswith(MAGIC):
        raise ValueError("Unsupported backup envelope")
    offset = len(MAGIC)
    return AESGCM(key).decrypt(data[offset:offset+12], data[offset+12:], MAGIC)


def pg_env(url):
    return {**os.environ, "PGHOST": url.host or "localhost", "PGPORT": str(url.port or 5432),
            "PGUSER": url.username or "", "PGPASSWORD": url.password or "", "PGCONNECT_TIMEOUT": "5"}


def dump_database(url):
    result = subprocess.run([shutil.which("pg_dump") or "pg_dump", "--format=custom", "--no-owner", "--no-acl", "--dbname", url.database],
                            env=pg_env(url), capture_output=True, check=True)
    return result.stdout


def restore_new(url, plaintext):
    import psycopg
    from psycopg import sql
    name = "dpr_restore_" + secrets.token_hex(6)
    with psycopg.connect(host=url.host, port=url.port, user=url.username, password=url.password,
                         dbname="postgres", autocommit=True, connect_timeout=5) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    subprocess.run([shutil.which("pg_restore") or "pg_restore", "--exit-on-error", "--no-owner", "--no-acl", "--dbname", name],
                   env=pg_env(url), input=plaintext, capture_output=True, check=True)
    return name


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["backup", "restore", "drill"])
    parser.add_argument("--file", type=Path, default=ROOT / ".local/protected.backup.enc")
    parser.add_argument("--key-file", type=Path, default=ROOT / ".local/backup-recovery.key")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    url = make_url(os.environ["MIGRATION_DATABASE_URL"])
    args.key_file.parent.mkdir(parents=True, exist_ok=True)
    if not args.key_file.exists():
        if args.command == "restore":
            raise ValueError("Recovery key missing")
        with args.key_file.open("xb") as f:
            f.write(os.urandom(32))
        os.chmod(args.key_file, 0o600)
    key = args.key_file.read_bytes()
    metrics = {"backup_seconds": "NOT TESTED", "restore_seconds": "NOT TESTED", "scope": "logical pg_dump + independent AES-256-GCM"}
    if args.command in {"backup", "drill"}:
        start = time.perf_counter()
        encrypted = encrypt_dump(dump_database(url), key)
        args.file.parent.mkdir(parents=True, exist_ok=True)
        # Replace atomically only after dump and authenticated encryption succeed.
        temporary = args.file.with_suffix(".tmp")
        temporary.write_bytes(encrypted)
        os.chmod(temporary, 0o600)
        temporary.replace(args.file)
        metrics.update(backup_seconds=time.perf_counter()-start, encrypted_bytes=len(encrypted))
    if args.command in {"restore", "drill"}:
        start = time.perf_counter()
        plaintext = decrypt_dump(args.file.read_bytes(), key)
        name = restore_new(url, plaintext)
        metrics.update(restore_seconds=time.perf_counter()-start, restored_database=name)
        sys.path.insert(0, str(ROOT / "apps/api"))
        from app.models import ImportRun, Member
        from app.config import Settings
        from app.crypto import build_protection
        from sqlalchemy import create_engine, func, select
        from sqlalchemy.orm import Session
        protection = build_protection(Settings.from_env())
        with Session(create_engine(url.set(database=name), hide_parameters=True)) as db:
            members = db.scalars(select(Member).order_by(Member.id)).all()
            for member in members:
                for field, envelope in member.protected_fields.items():
                    protection.decrypt(member.id, field, envelope)
            metrics.update(restored_records=len(members), all_fields_decrypt=True)
        print("Restored into a NEW lab database; retained for inspection: " + name)
    if args.command == "drill":
        tampered = bytearray(args.file.read_bytes())
        tampered[-1] ^= 1
        try:
            decrypt_dump(bytes(tampered), key)
        except Exception:
            metrics["tamper_rejected"] = True
        else:
            raise ValueError("Tamper verification failed")
    evidence = ROOT / "evidence/backup-restore.json"
    evidence.parent.mkdir(exist_ok=True)
    evidence.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Backup/restore failed ({type(exc).__name__}); no backup contents or credentials logged.", file=sys.stderr)
        sys.exit(1)
