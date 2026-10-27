"""Local role secrets: env first, otherwise Windows DPAPI outside the repository."""

import os
from pathlib import Path
import secrets

from infra.postgres.credentials import powershell
from infra.security import external_directory, secure_directory, write_private


ROLES = ("app_user","analyst_user","auditor_user","backup_user","admin_user","migration_user","scanner_user")


def role_environment(role: str) -> str:
    if role not in ROLES:
        raise ValueError("Unknown protected database role")
    return "DPR_" + role.upper() + "_PASSWORD"


def role_password(root: Path, role: str, *, create: bool = False) -> str:
    variable = role_environment(role)
    if os.environ.get(variable):
        password = os.environ[variable]
    else:
        directory = secure_directory(external_directory(str(root)) / "postgres" / "roles")
        path = directory / (role + ".credential.xml")
        if path.exists():
            password = powershell("""
$ErrorActionPreference='Stop'
$credential=[System.Management.Automation.PSSerializer]::Deserialize([System.IO.File]::ReadAllText($env:DPR_CREDENTIAL_PATH))
if ($credential -isnot [System.Management.Automation.PSCredential] -or $credential.UserName -ne $env:DPR_CREDENTIAL_ROLE) { throw 'Unexpected credential' }
[Console]::Write($credential.GetNetworkCredential().Password)
""", {"DPR_CREDENTIAL_PATH": str(path), "DPR_CREDENTIAL_ROLE": role})
        elif create:
            password = secrets.token_urlsafe(36)
            serialized = powershell("""
$ErrorActionPreference='Stop'
$secure=New-Object System.Security.SecureString
foreach ($char in $env:DPR_CREDENTIAL_INPUT.ToCharArray()) { $secure.AppendChar($char) }
$credential=New-Object System.Management.Automation.PSCredential($env:DPR_CREDENTIAL_ROLE, $secure)
[Console]::Write([System.Management.Automation.PSSerializer]::Serialize($credential))
""", {"DPR_CREDENTIAL_INPUT": password, "DPR_CREDENTIAL_ROLE": role})
            if password in serialized or "<SS " not in serialized:
                raise RuntimeError("Expected encrypted Windows credential")
            write_private(path, serialized.encode("utf-8"))
        else:
            raise ValueError("Role credential is required through env or local DPAPI")
    if len(password) < 20 or "\x00" in password or "\n" in password or "\r" in password:
        raise ValueError("Role credential must be a strong single-line value")
    return password
