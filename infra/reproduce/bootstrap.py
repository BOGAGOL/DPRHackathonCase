"""Install declared dependencies in two explicit, separate environments."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[2]


def python_bin(directory):
    return directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def checked(command, *, cwd=ROOT, timeout=900):
    """Commands here contain only public package names/paths, never credentials."""
    result = subprocess.run(command, cwd=cwd, capture_output=True, timeout=timeout,
                            env={**os.environ, "NEXT_TELEMETRY_DISABLED": "1"})
    if result.returncode:
        raise RuntimeError("Preparation command failed; dependency/build output withheld")


def setup():
    npm = shutil.which("npm")
    if not npm or not shutil.which("node"):
        raise RuntimeError("Install Node.js >=20.9 and npm first")
    result = subprocess.run([shutil.which("node"), "--version"], capture_output=True, text=True, check=True)
    version = tuple(int(v) for v in result.stdout.strip().lstrip("v").split(".")[:2])
    if version < (20, 9):
        raise ValueError("Node.js >=20.9 required")
    for directory, requirements in (
        (".venv", ("infra/requirements.txt", "app/requirements.txt", "infra/submission/requirements.txt")),
        (".venv-assessment", ("scanner/requirements.txt", "datagen/requirements.txt")),
    ):
        environment = ROOT / directory
        if environment.is_symlink():
            raise ValueError("Refusing environment symlink")
        if not python_bin(environment).is_file():
            venv.EnvBuilder(with_pip=True).create(environment)
        command = [str(python_bin(environment)), "-m", "pip", "install", "--disable-pip-version-check"]
        for requirement in requirements:
            command += ["-r", requirement]
        if directory == ".venv":
            command += ["-e", "toolkit"]
        print("Installing " + directory + " from declared dependencies...", flush=True)
        checked(command)
        checked([str(python_bin(environment)), "-m", "pip", "check"])
    print("Installing and building frontend from package-lock.json...", flush=True)
    checked([npm, "ci", "--no-fund", "--no-audit"], cwd=ROOT / "app/web")
    checked([npm, "run", "build"], cwd=ROOT / "app/web")
    destination = ROOT / "evidence/reproduction/generated"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "setup.json").write_text(json.dumps({
        "passed": True, "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "environments": [".venv", ".venv-assessment"], "pip_check": True,
        "npm_ci": True, "next_build": True, "database_or_keys_accessed": False,
    }, indent=2) + "\n", encoding="utf-8")
    print("Setup PASS. Next: python -m infra.reproduce verify --data <private 02_data.sql>")


def test():
    """Local regression suites; external service integrations remain explicit."""
    jobs = [
        (python_bin(ROOT / ".venv"), ["-m", "pytest", "-q", "--tb=short"]),
        (python_bin(ROOT / ".venv"), ["-m", "pytest", "-c", "app/pytest.ini", "app/tests", "-q", "--tb=short"]),
        (python_bin(ROOT / ".venv-assessment"), ["-m", "pytest", "scanner/tests", "datagen/tests", "-q", "--import-mode=importlib", "--tb=short"]),
    ]
    results = []
    for interpreter, arguments in jobs:
        if not interpreter.is_file():
            raise RuntimeError("Run setup first")
        results.append(subprocess.call([str(interpreter), *arguments], cwd=ROOT))
    return 0 if all(code == 0 for code in results) else 1
