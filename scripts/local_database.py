"""Isolated PostgreSQL lab clusters under .local; never connects to an existing server."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["start", "stop"])
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    import psycopg
    from psycopg import sql
    pg_ctl = shutil.which("pg_ctl")
    if not pg_ctl:
        raise RuntimeError("PostgreSQL binaries are required in PATH")
    bin_dir = Path(pg_ctl).parent
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    for label, port, username, password, database in [
        ("protected", 55432, "dpr_owner", os.environ["POSTGRES_PASSWORD"], "dpr_protected"),
        ("baseline", 55433, "baseline_owner", os.environ["BASELINE_DB_PASSWORD"], "dpr_baseline"),
    ]:
        directory = ROOT / ".local" / f"pg-{label}"
        if args.command == "stop":
            if (directory / "postmaster.pid").exists():
                subprocess.run([pg_ctl, "-D", str(directory), "-m", "fast", "-w", "stop"], check=True, **flags)
            continue
        if not (directory / "PG_VERSION").exists():
            ROOT.joinpath(".local").mkdir(exist_ok=True)
            password_file = ROOT / ".local" / f".init-{label}"
            try:
                with password_file.open("x", encoding="utf-8") as f:
                    f.write(password)
                os.chmod(password_file, 0o600)
                subprocess.run([str(bin_dir / ("initdb.exe" if os.name == "nt" else "initdb")), "-D", str(directory),
                                "-U", username, "--auth=scram-sha-256", "--pwfile=" + str(password_file), "-E", "UTF8", "--locale=C"], check=True, **flags)
            finally:
                password_file.unlink(missing_ok=True)
            with (directory / "postgresql.conf").open("a", encoding="utf-8") as f:
                f.write("\nlog_statement = 'none'\nlog_min_error_statement = 'panic'\nlog_parameter_max_length_on_error = 0\n")
        if not (directory / "postmaster.pid").exists():
            subprocess.run([pg_ctl, "-D", str(directory), "-l", str(ROOT / ".local" / f"{label}-postgres.log"),
                            "-o", f"-h 127.0.0.1 -p {port}", "-w", "start"], check=True, **flags)
        with psycopg.connect(host="127.0.0.1", port=port, user=username, password=password, dbname="postgres", autocommit=True) as connection:
            if not connection.execute("SELECT 1 FROM pg_database WHERE datname=%s", (database,)).fetchone():
                connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        print(f"{label} lab ready at 127.0.0.1:{port} (development, no TLS)")


if __name__ == "__main__":
    main()
