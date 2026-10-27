"""Windows DPAPI credential storage outside Git; plaintext only in process memory/env."""

import os
from pathlib import Path
import subprocess

from infra.security import external_directory, secure_directory, write_private


def powershell(script: str, environment: dict) -> str:
    if os.name != "nt":
        raise RuntimeError("The local credential helper requires Windows DPAPI")
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                            env={**os.environ, **environment}, capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise RuntimeError("Windows credential operation failed; output withheld")
    return result.stdout


def save_password(root: Path, password: str) -> None:
    destination = secure_directory(external_directory(str(root)) / "postgres") / "admin.credential.xml"
    serialized = powershell("""
$ErrorActionPreference = 'Stop'
$secure = New-Object System.Security.SecureString
foreach ($char in $env:DPR_CREDENTIAL_INPUT.ToCharArray()) { $secure.AppendChar($char) }
$credential = New-Object System.Management.Automation.PSCredential('postgres', $secure)
[Console]::Write([System.Management.Automation.PSSerializer]::Serialize($credential))
""", {"DPR_CREDENTIAL_INPUT": password})
    if password in serialized or "<SS " not in serialized:
        raise RuntimeError("Expected DPAPI-protected credential serialization")
    write_private(destination, serialized.encode("utf-8"))


def load_password(root: Path) -> str:
    path = external_directory(str(root)) / "postgres/admin.credential.xml"
    password = powershell("""
$ErrorActionPreference = 'Stop'
$credential = [System.Management.Automation.PSSerializer]::Deserialize([System.IO.File]::ReadAllText($env:DPR_CREDENTIAL_PATH))
if ($credential -isnot [System.Management.Automation.PSCredential] -or $credential.UserName -ne 'postgres') { throw 'Invalid credential type' }
[Console]::Write($credential.GetNetworkCredential().Password)
""", {"DPR_CREDENTIAL_PATH": str(path)})
    if not password:
        raise RuntimeError("Empty local credential")
    return password
