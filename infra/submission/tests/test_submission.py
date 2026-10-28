import base64
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

import pytest

from infra.submission import inventory, package, sbom
from infra.submission import __main__ as cli


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    files = {
        "README.md": "# Fixture\n[Guide](docs/guide.md)\n",
        "docs/guide.md": "# Guide\n",
        "app/backend/service_app/main.py": "# invented test fixture, never a service\n",
        "infra/compose.yaml": "services:\n  bao:\n    image: openbao/openbao:2.5.5\n",
        "toolkit/dprcrypto/codec.py": "# fixture\n",
        "infra/requirements.txt": "cryptography>=46,<47\npytest==9.0.2\n",
        "app/requirements.txt": "httpx==0.28.1\n",
        "scanner/requirements.txt": "pytest==8.4.2\n",
        "toolkit/pyproject.toml": '[project]\ndependencies=["httpx>=0.28,<0.29"]\n[build-system]\nrequires=["setuptools>=77"]\n',
        "app/web/package-lock.json": json.dumps(
            {
                "lockfileVersion": 3,
                "packages": {
                    "": {"name": "fixture"},
                    "node_modules/example": {
                        "version": "1.2.3",
                        "license": "MIT",
                        "integrity": "sha512-" + base64.b64encode(b"x" * 64).decode(),
                    },
                },
            }
        ),
        "docs/submission/requirements.json": json.dumps(
            {
                "deliverables": [
                    {"id": "D03", "status": "DRAFT", "paths": ["docs/guide.md"]}
                ]
            }
        ),
    }
    for name, content in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        cwd=root,
        check=True,
        capture_output=True,
    )
    sbom.generate(root)
    return root


@pytest.mark.parametrize(
    "name",
    [
        "sql/baseline/02_data.sql",
        "docs/copy.sql",
        "app/.env",
        "app/local.env",
        "app/.pgpass",
        "app/.netrc",
        "app/id_ed25519",
        "infra/openbao/tokens/service.json",
        "app/runtime.log",
        "app/.DS_Store",
        "app/.local/account.json",
        "infra/private/token.json",
        "creds.json",
        "docs/credentials.json",
        "app/service-b-protected-accounts.json",
        "archive/README.md",
        "docs/reference/book.py",
        "../file.py",
        "/file.py",
        "C:/file.py",
        "app\\file.py",
        "evidence/submission/generated/check.json",
        "docs/input.dump",
        "app/node_modules/p/package.json",
    ],
)
def test_private_legacy_raw_data_and_path_traversal_are_excluded(name):
    assert not inventory.allowed(name)


@pytest.mark.parametrize(
    "name",
    [
        "README.md",
        "app/.env.example",
        "sql/baseline/01_schema.sql",
        "sql/protected/03_analyst_suppression.sql",
        "scripts/backup/runner.py",
        "docs/report/DRAFT.md",
        "verify/scan_config.toml",
    ],
)
def test_reviewed_active_source_is_allowed(name):
    assert inventory.allowed(name)


def test_declared_python_ranges_are_not_fabricated_as_resolved_versions(tree):
    components = sbom.python_components(tree)
    crypto = next(c for c in components if c["name"] == "cryptography")
    assert "version" not in crypto
    pytest_versions = {c["version"] for c in components if c["name"] == "pytest"}
    assert pytest_versions == {"8.4.2", "9.0.2"}
    node = sbom.node_components(tree)[0]
    assert node["hashes"][0]["content"] == (b"x" * 64).hex()
    assert sbom.infrastructure_components(tree)[0]["version"] == "2.5.5"


def test_sbom_is_deterministic_and_detects_changed_input_or_artifact(tree):
    before = (tree / "docs/sbom/python-declared.cdx.json").read_bytes()
    sbom.generate(tree)
    assert (
        tree / "docs/sbom/python-declared.cdx.json"
    ).read_bytes() == before and sbom.fresh(tree)
    (tree / "docs/sbom/python-declared.cdx.json").write_text("{}")
    assert not sbom.fresh(tree)
    sbom.generate(tree)
    (tree / "infra/requirements.txt").write_text("cryptography==46.0.5\n")
    assert not sbom.fresh(tree)


def test_npm_wrong_lock_format_is_rejected(tree):
    p = tree / "app/web/package-lock.json"
    d = json.loads(p.read_text())
    d["lockfileVersion"] = 2
    p.write_text(json.dumps(d))
    with pytest.raises(ValueError):
        sbom.node_components(tree)


def test_links_and_secret_screen_fail_without_echoing_the_value(tree):
    (tree / "docs/guide.md").write_text("[missing](absent.md)\n" + "hvs." + "A" * 32)
    report = package.check(tree)
    assert not report["passed"]
    assert report["broken_links"] == [
        {"document": "docs/guide.md", "target": "absent.md"}
    ]
    assert report["secret_findings"][0]["value_withheld"]
    assert "hvs." + "A" * 32 not in json.dumps(report)
    with pytest.raises(ValueError):
        package.build(tree, tree.parent / "blocked")
    assert not (tree.parent / "blocked").exists()


def test_quality_does_not_certify_pending_pdf_slides_or_benchmark(tree):
    report = package.check(tree)
    assert (
        report["passed"]
        and report["release_status"] == "REVIEW_REQUIRED"
        and report["pending_deliverables"] == ["D03"]
    )
    (tree / "docs/guide.md").unlink()
    assert not package.check(tree)["checks"]["required_working_documents_present"]


def test_public_docs_must_not_link_to_excluded_private_archive(tree):
    hidden = tree / "archive/old.md"
    hidden.parent.mkdir()
    hidden.write_text("historical")
    (tree / "docs/guide.md").write_text("[old](../archive/old.md)\n")
    report = package.check(tree)
    assert (
        not report["passed"]
        and report["broken_links"][0]["reason"] == "target_excluded_from_package"
    )


def test_package_excludes_even_tracked_secrets_and_dataset_and_verifies_hashes(tree):
    for name in (
        "creds.json",
        "sql/baseline/02_data.sql",
        "docs/reference/book.txt",
        "archive/old.txt",
        "app/.env",
    ):
        p = tree / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("private sentinel")
        subprocess.run(
            ["git", "add", "--", name], cwd=tree, check=True, capture_output=True
        )
    output = tree.parent / "package"
    result = package.build(tree, output)
    assert result["passed"] and result["release_status"] == "REVIEW_REQUIRED"
    with zipfile.ZipFile(result["archive"]) as archive:
        assert all(
            "private sentinel".encode() not in archive.read(name)
            for name in archive.namelist()
        )
        manifest = json.loads(archive.read("SOURCE_MANIFEST.json"))
        assert "sql/baseline/02_data.sql" not in manifest["files"]
        assert all(
            hashlib.sha256(archive.read(name)).hexdigest() == item["sha256"]
            for name, item in manifest["files"].items()
        )
    with pytest.raises(ValueError):
        package.build(tree, output)
    with pytest.raises(ValueError):
        package.build(tree, tree)


def test_extracted_package_checks_work_without_git_and_preserve_pending_status(tree):
    result = package.build(tree, tree.parent / "first-package")
    extracted = tree.parent / "extracted"
    extracted.mkdir()
    with zipfile.ZipFile(result["archive"]) as archive:
        archive.extractall(extracted)
    assert inventory.git_revision(extracted) is None
    report = package.check(extracted)
    assert report["passed"] and report["release_status"] == "REVIEW_REQUIRED"
    rebuilt = package.build(extracted, tree.parent / "rebuilt")
    with zipfile.ZipFile(rebuilt["archive"]) as archive:
        manifest = json.loads(archive.read("SOURCE_MANIFEST.json"))
        assert manifest["source_commit"] is None and manifest["source_tree_dirty"]


def test_external_source_link_is_refused(tree):
    outside = tree.parent / "outside.py"
    outside.write_text("private sentinel")
    try:
        (tree / "app/link.py").symlink_to(outside)
    except OSError:
        pytest.skip("OS does not permit creating an unprivileged symbolic link")
    with pytest.raises(ValueError):
        inventory.candidates(tree)


def test_text_identity_accepts_checkout_line_endings_only(tmp_path):
    p = tmp_path / "x.txt"
    p.write_bytes(b"one\ntwo\n")
    digest = inventory.text_sha(p)
    p.write_bytes(b"one\r\ntwo\r\n")
    assert inventory.text_sha(p) == digest
    p.write_bytes(b"different\n")
    assert inventory.text_sha(p) != digest


@pytest.mark.parametrize("command", ["sbom", "check", "build"])
def test_cli_reports_success_and_redacts_failures(tree, monkeypatch, capsys, command):
    monkeypatch.setattr(cli, "REPO", tree)
    argv = [command, "--output", str(tree.parent / "cli-output")]
    assert cli.main(argv) == 0
    if command == "sbom":
        target = cli.sbom
        function = "generate"
    elif command == "check":
        target = cli.package
        function = "check"
    else:
        target = cli.package
        function = "build"

    def fail(*args):
        raise RuntimeError("private sentinel")

    monkeypatch.setattr(target, function, fail)
    assert cli.main(argv) == 1
    assert (
        "private sentinel"
        not in capsys.readouterr().out
        + (tree / "evidence/submission/generated" / (command + ".json")).read_text()
    )
