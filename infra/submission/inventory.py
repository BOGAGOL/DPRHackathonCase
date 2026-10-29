"""Narrow source selection; never infer public safety from .gitignore alone."""

import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
from urllib.parse import unquote

ROOT_FILES = {
    "README.md",
    "AGENTS.md",
    "LICENSE",
    "LICENSE-DOCS.md",
    "THIRD_PARTY_NOTICES.md",
    "Makefile",
    "pytest.ini",
    ".gitignore",
    ".gitattributes",
    ".gitleaks.toml",
    ".dockerignore",
    ".env.example",
}
ROOTS = {
    "app",
    "benchmark",
    "datagen",
    "docs",
    "evidence",
    "infra",
    "migration",
    "policy",
    "scanner",
    "sql",
    "toolkit",
    "verify",
}
PRIVATE_PARTS = {
    ".git",
    ".venv",
    ".venv-assessment",
    ".venv-benchmark",
    "venv",
    "node_modules",
    ".next",
    ".local",
    ".secrets",
    "secrets",
    "private",
    "tokens",
    "__pycache__",
    ".pytest_cache",
    "test-results",
    "playwright-report",
}
PRIVATE_NAMES = {
    "creds.json",
    "credentials.json",
    "accounts.md",
    "database-credentials.json",
    "init-material.json",
    "operator.env",
    "compose.env",
    "app.env",
    "setup.env",
    "migration.env",
    ".pgpass",
    "pgpass.conf",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "id_rsa",
    "id_ed25519",
    ".ds_store",
    "thumbs.db",
    "desktop.ini",
}
PRIVATE_SUFFIXES = {
    ".key",
    ".pem",
    ".pfx",
    ".p12",
    ".ppk",
    ".dump",
    ".backup",
    ".dprbak",
    ".db",
    ".sqlite",
    ".pyc",
    ".tsbuildinfo",
    ".enc",
    ".env",
    ".log",
    ".pid",
    ".sock",
}
EXCLUDE_PREFIXES = ("docs/reference/", "evidence/submission/generated/", "evidence/reproduction/generated/")
PUBLIC_REPORTS = {"evidence/secrets/plaintext-scan.json"}


def text_sha(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def source_names(root):
    if git_revision(root):
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=root,
            capture_output=True,
            check=True,
        )
        return sorted(
            set(name.decode("utf-8") for name in result.stdout.split(b"\0") if name)
        )
    # Extracted submission packages intentionally do not contain .git. Traverse
    # active roots only, pruning private/cache/reference directories before read.
    names = [name for name in ROOT_FILES if (root / name).is_file()]
    for prefix in sorted(ROOTS | {"scripts/backup"}):
        if not (root / prefix).is_dir():
            continue
        for base, dirs, files in os.walk(root / prefix, followlinks=False):
            dirs[:] = [
                name
                for name in dirs
                if (name.lower() not in PRIVATE_PARTS or
                    (Path(base) / name).relative_to(root).as_posix() == "evidence/secrets")
                and not name.lower().endswith((".egg-info", ".dist-info"))
                and not (Path(base) / name)
                .relative_to(root)
                .as_posix()
                .startswith(EXCLUDE_PREFIXES)
                and (Path(base) / name).resolve().is_relative_to(root.resolve())
            ]
            names.extend(
                (Path(base) / name).relative_to(root).as_posix() for name in files
            )
    return sorted(set(names))


def git_revision(root):
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=root,
            capture_output=True,
            text=True,
        )
        if top.returncode or Path(top.stdout.strip()).resolve() != root.resolve():
            return None
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True
        )
        return head.stdout.strip() if head.returncode == 0 else None
    except OSError:
        return None


def allowed(name):
    """Allow active source roots, then deny private/runtime/data paths explicitly."""
    path = PurePosixPath(name)
    if (
        not name
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in name
        or ":" in name
    ):
        return False
    parts = tuple(part.lower() for part in path.parts)
    base = parts[-1]
    # One reviewed metadata-only scan receipt lives under a directory called
    # 'secrets'. Do not admit arbitrary neighbours or private operational folders.
    if any((part in PRIVATE_PARTS and not (name in PUBLIC_REPORTS and part == "secrets")) or
           part.endswith((".egg-info", ".dist-info")) for part in parts) or base in PRIVATE_NAMES:
        return False
    if name.startswith(EXCLUDE_PREFIXES) or name == "sql/baseline/02_data.sql":
        return False
    if base.endswith(".credential.xml") or (
        base.startswith("service-b-") and base.endswith("-accounts.json")
    ):
        return False
    if base.startswith(".env") and base != ".env.example":
        return False
    if path.suffix.lower() in PRIVATE_SUFFIXES or base.endswith(
        (".sql.gz", ".tar", ".tar.gz", ".zip")
    ):
        return False
    if path.suffix.lower() == ".sql" and not (
        name in {"sql/baseline/01_schema.sql", "sql/baseline/03_validasi.sql"}
        or name.startswith(("sql/protected/", "sql/roles/", "scanner/sql/"))
    ):
        return False
    return (
        name in ROOT_FILES
        or path.parts[0] in ROOTS
        or name.startswith("scripts/backup/")
    )


def candidates(root):
    files = []
    for name in source_names(root):
        if not allowed(name):
            continue
        path = root / name
        if not path.exists():
            continue
        if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
            raise ValueError("Source link leaves reviewed tree")
        files.append(name)
    return files


def secret_findings(root, names):
    """Conservative content screen, not a complete secret/history/PII audit."""
    token = re.compile(
        rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|hvs\.[A-Za-z0-9_-]{20,}|hvb\.[A-Za-z0-9_-]{20,})"
    )
    key = re.compile(
        rb"-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----\r?\n[A-Za-z0-9+/=\r\n]{64,}-----END"
    )
    findings = []
    for name in names:
        raw = (root / name).read_bytes()
        if token.search(raw) or key.search(raw):
            findings.append(
                {"path": name, "kind": "credential_pattern", "value_withheld": True}
            )
    return findings


def broken_links(root, names):
    broken = []
    selected = set(names)
    for name in names:
        if not name.endswith(".md"):
            continue
        text = (root / name).read_text(encoding="utf-8-sig")
        text = re.sub(r"```.*?```", "", text, flags=re.S)
        for target in re.findall(r"!?\[[^\]]*\]\(([^\n]+?)\)", text):
            target = target.strip().strip("<>").split("#", 1)[0]
            if not target or re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", target):
                continue
            path = (root / name).parent / unquote(target)
            if not path.exists():
                broken.append({"document": name, "target": target})
            elif (
                path.is_file()
                and path.resolve().is_relative_to(root.resolve())
                and path.resolve().relative_to(root.resolve()).as_posix()
                not in selected
            ):
                broken.append(
                    {
                        "document": name,
                        "target": target,
                        "reason": "target_excluded_from_package",
                    }
                )
    return broken
