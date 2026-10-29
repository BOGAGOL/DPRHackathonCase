"""Private storage and a streaming COPY parser; SQL is never executed."""
import os
from pathlib import Path
import re
import subprocess

from datagen.model import COLUMNS
from scanner.sources import copy_unescape

ROOT = Path(__file__).resolve().parents[1]


def private_path(path):
    directory = os.environ.get("DPR_PRIVATE_DIR")
    if not directory:
        raise ValueError("DPR_PRIVATE_DIR required")
    root = Path(directory).resolve()
    result = Path(path).resolve()
    if root == ROOT or root.is_relative_to(ROOT) or result == root or not result.is_relative_to(root):
        raise ValueError("Sensitive files must stay under external DPR_PRIVATE_DIR")
    return result


def expand_dump(artifact, output):
    artifact, output = private_path(artifact), private_path(output)
    with artifact.open("rb") as handle:
        if handle.read(5) != b"PGDMP":
            raise ValueError("Expected custom pg_dump snapshot")
    output.parent.mkdir(parents=True, exist_ok=True)
    with artifact.open("rb") as source, output.open("xb") as target:
        completed = subprocess.run(["docker", "exec", "-i", "pg-dpr", "pg_restore", "--data-only",
                                    "--no-owner", "--no-privileges", "--file=-"],
                                   stdin=source, stdout=target, stderr=subprocess.PIPE)
    if completed.returncode:
        raise ValueError("Snapshot expansion failed (stderr withheld)")
    return output


def copy_rows(path):
    """Text COPY from this baseline schema, including PostgreSQL escaping/NULL."""
    active = False
    tables = 0
    with Path(path).open(encoding="utf-8", newline="") as handle:
        for line in handle:
            if active:
                raw = line.rstrip("\r\n")
                if raw == r"\.":
                    active = False
                    continue
                fields = raw.split("\t")
                if len(fields) != len(columns):
                    raise ValueError("COPY field count differs from schema")
                values = [None if value == r"\N" else copy_unescape(value) for value in fields]
                yield dict(zip(columns, values))
            elif line.startswith("COPY "):
                header = re.fullmatch(r'COPY (?:public|"public")\.(?:anggota|"anggota") \((.+)\) FROM stdin;\s*', line)
                if not header:
                    raise ValueError("Unsupported COPY table or format")
                columns = [name.strip().strip('"') for name in header[1].split(",")]
                if len(columns) != len(COLUMNS) or set(columns) != set(COLUMNS):
                    raise ValueError("COPY columns differ from baseline schema")
                tables += 1
                active = True
            elif line.lstrip().upper().startswith("INSERT INTO"):
                raise ValueError("This verifier requires text COPY, not INSERT expressions")
    if active or tables != 1:
        raise ValueError("Truncated or missing/duplicate COPY table")
