"""Generate entirely synthetic load-test data in NEW databases; never modifies organizer data."""
import argparse
import hashlib
import os
from pathlib import Path
import secrets
import subprocess
import sys

from dotenv import load_dotenv
import psycopg
from psycopg import sql
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api"))
from app.config import Settings
from app.crypto import build_protection
from app.ingestion import COLUMNS, import_baseline, protect_rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=10000)
    args = parser.parse_args()
    if not 1000 <= args.rows <= 100000:
        parser.error("Use 1000–100000 entirely synthetic records")
    load_dotenv(ROOT / ".env")
    urls = {}
    for mode, variable in [("baseline", "BASELINE_DATABASE_URL"), ("protected", "MIGRATION_DATABASE_URL")]:
        url = make_url(os.environ[variable])
        name = f"dpr_scale_{mode}_" + secrets.token_hex(4)
        with psycopg.connect(host=url.host, port=url.port, user=url.username, password=url.password,
                             dbname="postgres", autocommit=True, connect_timeout=5) as conn:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        urls[variable] = url.set(database=name).render_as_string(hide_password=False)
    env_file = ROOT / ".local/scale.env"
    with env_file.open("w", encoding="utf-8") as f:
        for name, url in urls.items():
            f.write(f"{name}='{url}'\n")
        f.write(f"DATABASE_URL='{urls['MIGRATION_DATABASE_URL']}'\n")
    os.chmod(env_file, 0o600)
    subprocess.run([sys.executable, "-m", "alembic", "-c", "apps/api/alembic.ini", "upgrade", "head"], cwd=ROOT,
                   env={**os.environ, "MIGRATION_DATABASE_URL": urls["MIGRATION_DATABASE_URL"]}, check=True)
    rows = []
    for i in range(1, args.rows+1):
        row = {f: f"uji-beban-{f}-{i}" for f in COLUMNS}
        row.update(nama=f"Anggota Uji Beban {i:06d}", ruangan=f"UJI-{i:06d}", no_ktp=f"{i:014d}",
                   rekening=f"{i:018d}", email=f"uji{i}@example.test", handphone=f"08{i:010d}",
                   tanggal_lahir="1980-01-01", tanggal_pernikahan="2010-01-01" if i % 2 else None)
        rows.append(row)
    import_baseline(create_engine(urls["BASELINE_DATABASE_URL"], hide_parameters=True), rows)
    settings = Settings.from_env()
    with Session(create_engine(urls["MIGRATION_DATABASE_URL"], hide_parameters=True)) as session:
        protect_rows(session, build_protection(settings), rows, hashlib.sha256(f"synthetic-generator-v1:{args.rows}".encode()).hexdigest())
    print(f"Generated and round-trip verified {args.rows} synthetic records in new databases; use --env-file .local/scale.env")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Scale lab failed ({type(exc).__name__}); values withheld.", file=sys.stderr)
        sys.exit(1)
