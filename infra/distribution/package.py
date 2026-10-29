"""Package product source and recorded measurements with integrity verification."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

from .inventory import candidates, broken_links, secret_findings, git_revision
from .sbom import fresh


def check(root):
    names = candidates(root)
    links = broken_links(root, names)
    secrets = secret_findings(root, names)
    required = json.loads((root / "infra/distribution/manifest.json").read_text(encoding="utf-8"))["required_paths"]
    missing = [{"path": name} for name in required if not (root / name).exists()]
    checks = {
        "active_sources_present": all(
            (root / name).exists()
            for name in (
                "app/backend/service_app/main.py",
                "infra/compose.yaml",
                "toolkit/dprcrypto/codec.py",
            )
        ),
        "obsolete_runtime_absent": not any(
            (root / name).exists()
            for name in ("apps", "infrastructure", "docker-compose.yml")
        ),
        "document_links_valid": not links,
        "required_product_files_present": not missing,
        "no_credential_patterns_in_selected_files": not secrets,
        "sbom_inputs_current": fresh(root),
    }
    return {
        "schema_version": 1,
        "passed": all(checks.values()),
        "checks": checks,
        "selected_files": len(names),
        "broken_links": links,
        "missing_paths": missing,
        "secret_findings": secrets,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "scope": "Source integrity and documentation checks; runtime/security results are reported separately",
    }


def build(root, output):
    report = check(root)
    if not report["passed"]:
        raise ValueError(
            "Product source checks failed; inspect the sanitized check report"
        )
    names = candidates(root)
    output = Path(output).resolve()
    if output == root.resolve() or root.resolve().is_relative_to(output):
        raise ValueError(
            "Use a dedicated output directory, not the repository or its parent"
        )
    if output.exists() and any(output.iterdir()):
        raise ValueError(
            "Output directory must be new/empty; previous packages are preserved"
        )
    output.mkdir(parents=True, exist_ok=True)
    revision = git_revision(root)
    dirty = (
        bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root))
        if revision
        else True
    )
    files = {name: (root / name).read_bytes() for name in names}
    manifest = {
        "schema_version": 1,
        "source_commit": revision,
        "source_tree_dirty": dirty,
        "status": report["status"],
        "files": {
            name: {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
            for name, raw in files.items()
        },
        "exclusions": [
            "organizer dataset",
            "private credentials/keys/dumps",
            "Git metadata",
            "local environments/caches",
            "legacy archive",
            "third-party book reference",
            "generated quality reports",
        ],
        "notice": "Product source, executable tests and recorded measurements. Evaluator application accounts are intentionally included separately from infrastructure secrets.",
    }
    archive = output / (
        "dpr-source-" + (revision[:12] if revision else "unversioned") + ".zip"
    )
    with zipfile.ZipFile(
        archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as stream:
        for name, raw in files.items():
            stream.writestr(name, raw)
        stream.writestr("SOURCE_MANIFEST.json", json.dumps(manifest, indent=2) + "\n")
        stream.writestr("QUALITY_REPORT.json", json.dumps(report, indent=2) + "\n")
    with zipfile.ZipFile(archive) as stream:
        if stream.testzip() is not None:
            raise ValueError("Archive integrity test failed")
        if any(
            hashlib.sha256(stream.read(name)).hexdigest() != item["sha256"]
            for name, item in manifest["files"].items()
        ):
            raise ValueError("Archive manifest mismatch")
    result = {
        "schema_version": 1,
        "passed": True,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "archive": str(archive),
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "size_bytes": archive.stat().st_size,
        "files": len(files),
        "status": report["status"],
    }
    (output / "build-report.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result
