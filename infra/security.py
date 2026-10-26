"""Keep bootstrap material outside the checkout, readable only by its operator."""

import os
from pathlib import Path
import subprocess


REPO = Path(__file__).resolve().parents[1]


def external_directory(value: str | None) -> Path:
    if not value or not Path(value).is_absolute():
        raise ValueError("DPR_SECRETS_DIR must be an absolute path outside the repository")
    directory = Path(value).resolve()
    if directory.is_relative_to(REPO) or REPO.is_relative_to(directory):
        raise ValueError("DPR_SECRETS_DIR must not contain or be inside the repository")
    if directory == Path.home().resolve():
        raise ValueError("Use a dedicated secrets directory, not your home directory")
    return directory


def secure_directory(directory: Path) -> Path:
    # Validate each child too: an existing junction/symlink may point into Git.
    directory = external_directory(str(directory))
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "nt":
        # A new DACL removes inherited AND existing grants. No secret in arguments.
        script = """
$ErrorActionPreference = 'Stop'
$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$acl = New-Object System.Security.AccessControl.DirectorySecurity
$acl.SetOwner($sid)
$acl.SetAccessRuleProtection($true, $false)
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule($sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
$acl.AddAccessRule($rule)
[System.IO.Directory]::SetAccessControl($env:DPR_ACL_TARGET, $acl)
"""
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            env={**os.environ, "DPR_ACL_TARGET": str(directory)},
            capture_output=True, check=False,
        )
        if result.returncode:
            raise RuntimeError("Cannot restrict secrets directory ACL; no secrets were written")
    else:
        directory.chmod(0o700)
    return directory


def write_private(path: Path, content: bytes) -> None:
    # Exclusive creation prevents accidental replacement of recovery material.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
