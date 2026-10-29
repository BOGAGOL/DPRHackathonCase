"""Narrow policy checks without opening the organizer dataset."""

from pathlib import Path
import re
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parents[2]
DATASET = "sql/baseline/02_data.sql"


def test_s06_and_public_attachment_exclude_only_the_authorized_file():
    config = tomllib.loads((ROOT / "verify/scan_config.toml").read_text(encoding="utf-8"))
    assert config["version"] == 1
    assert config["plaintext_s06"]["exclude_exact_paths"] == [DATASET]
    assert config["public_attachment"]["exclude_exact_paths"] == [DATASET]


def test_gitleaks_dataset_allowlist_is_exact():
    config = tomllib.loads((ROOT / ".gitleaks.toml").read_text(encoding="utf-8"))
    entries = [entry for entry in config["allowlists"]
               if "Organizer synthetic" in entry["description"]]
    assert len(entries) == 1
    pattern, = entries[0]["paths"]
    assert re.search(pattern, DATASET)
    for other in ("sql/baseline/01_schema.sql", DATASET + ".bak", "copy/" + DATASET,
                  "sql/protected/02_data.sql", "evidence/02_data.sql"):
        assert not re.search(pattern, other)


def test_git_archive_excludes_dataset_from_attachments(tmp_path):
    # Exercise the shipped attributes in an isolated repo, including when this
    # test is run from a source ZIP without its original Git history or dataset.
    (tmp_path / ".gitattributes").write_bytes((ROOT / ".gitattributes").read_bytes())
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True,
                   capture_output=True, text=True)
    result = subprocess.run(["git", "check-attr", "export-ignore", "--", DATASET],
                            cwd=tmp_path, check=True, capture_output=True, text=True)
    assert result.stdout.strip() == DATASET + ": export-ignore: set"
