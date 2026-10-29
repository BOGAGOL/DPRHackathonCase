"""Build an allowlisted, secret-free archive for the non-Git Ubuntu deployment."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[2]
FILES = (
    "app/scripts/serve.py", "app/scripts/run_runtime.sh", "app/backend/service_app/token_source.py",
    "app/deploy/token_refresh.py", "app/deploy/dpr-token-refresh.service", "app/deploy/dpr-token-refresh.timer",
    "app/deploy/token-auto.conf", "app/deploy/install_token_refresh.sh",
)
BASE_FILES = FILES[:2]


def build(destination, base_commit="7a37210"):
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    content = {name: (ROOT / name).read_bytes().replace(b"\r\n", b"\n") for name in FILES}
    base = {name: subprocess.check_output(["git", "show", base_commit + ":" + name], cwd=ROOT) for name in BASE_FILES}
    manifest = {"source_commit": commit, "base_commit": base_commit,
                "files": {name: hashlib.sha256(value).hexdigest() for name, value in content.items()},
                "base_files": {name: hashlib.sha256(value).hexdigest() for name, value in base.items()}}
    content["manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    content["apply.sh"] = b'#!/usr/bin/env bash\nset -euo pipefail\nstage="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"\nexec bash "$stage/app/deploy/install_token_refresh.sh" "$stage"\n'
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(destination, "w") as archive:
        for name, value in content.items():
            info = tarfile.TarInfo("dpr-token-autorefresh/" + name)
            info.size, info.mode = len(value), 0o644
            archive.addfile(info, io.BytesIO(value))
    return {"archive": str(destination), "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            "source_commit": commit, "runtime_files": len(FILES), "secrets_or_dataset_included": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "app/.local/dpr-token-autorefresh.tar")
    args = parser.parse_args()
    print(json.dumps(build(args.output)))


if __name__ == "__main__":
    main()
