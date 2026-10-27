"""Environment credentials, plus explicit Windows DPAPI development helpers."""

import base64
import json
import os
from pathlib import Path
import secrets

from infra.postgres.credentials import load_password, powershell
from infra.protected.credentials import role_password
from infra.security import external_directory, secure_directory, write_private
from .crypto import BackupError


KEY_VARS = ("DPR_BACKUP_KEY_B64", "DPR_BACKUP_HMAC_KEY_B64")


def local_keys(root, *, create=False):
    directory = secure_directory(external_directory(str(root)) / "backup-keys")
    for variable in KEY_VARS:
        path = directory / (variable.lower() + ".credential.xml")
        if not path.exists() and create:
            value = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
            serialized = powershell("""
$ErrorActionPreference='Stop'
$secure=New-Object System.Security.SecureString
foreach ($char in $env:DPR_CREDENTIAL_INPUT.ToCharArray()) { $secure.AppendChar($char) }
$credential=New-Object System.Management.Automation.PSCredential($env:DPR_CREDENTIAL_ROLE,$secure)
[Console]::Write([System.Management.Automation.PSSerializer]::Serialize($credential))
""", {"DPR_CREDENTIAL_INPUT": value, "DPR_CREDENTIAL_ROLE": variable})
            if value in serialized or "<SS " not in serialized:
                raise BackupError("invalid_dpapi_serialization")
            write_private(path, serialized.encode("utf-8"))
        value = powershell("""
$ErrorActionPreference='Stop'
$credential=[System.Management.Automation.PSSerializer]::Deserialize([System.IO.File]::ReadAllText($env:DPR_CREDENTIAL_PATH))
if ($credential -isnot [System.Management.Automation.PSCredential] -or $credential.UserName -ne $env:DPR_CREDENTIAL_ROLE) { throw 'Unexpected credential' }
[Console]::Write($credential.GetNetworkCredential().Password)
""", {"DPR_CREDENTIAL_PATH": str(path), "DPR_CREDENTIAL_ROLE": variable})
        os.environ[variable] = value
    return backup_keys()


def backup_keys():
    try:
        values = tuple(base64.b64decode(os.environ[name], validate=True) for name in KEY_VARS)
        if any(len(key) != 32 for key in values) or values[0] == values[1]:
            raise ValueError()
        return values
    except (KeyError, ValueError):
        raise BackupError("two_distinct_32_byte_backup_keys_required") from None


def parameters(database, *, admin=False, local=False):
    root = external_directory(os.environ.get("DPR_SECRETS_DIR")) if local else None
    user = os.environ.get("DPR_RESTORE_USER", "postgres") if admin else "backup_user"
    password = os.environ.get("DPR_RESTORE_PASSWORD" if admin else "DPR_BACKUP_PASSWORD")
    if local and not password:
        password = load_password(root) if admin else role_password(root, "backup_user")
    ca = os.environ.get("PGSSLROOTCERT") or (str(root / "postgres/tls/ca.crt") if root else "")
    port = int(os.environ.get("PGPORT", "5433"))
    if not password or not Path(ca).is_file() or not 1 <= port <= 65535:
        raise BackupError("verified_tls_database_credentials_required")
    return {"host": os.environ.get("PGHOST", "127.0.0.1"), "port": port, "dbname": database,
            "user": user, "password": password, "sslrootcert": ca, "sslmode": "verify-full",
            "gssencmode": "disable", "connect_timeout": 10}


def artifact_store(value):
    path = external_directory(value)
    marker = path / ".dpr-backup-store.json"
    if path.exists() and not marker.exists() and any(path.iterdir()):
        raise BackupError("use_a_dedicated_empty_backup_directory")
    path = secure_directory(path)
    if not marker.exists():
        write_private(marker, json.dumps({"format": "dpr-backup-store-v1"}).encode())
    elif json.loads(marker.read_text()) != {"format": "dpr-backup-store-v1"}:
        raise BackupError("invalid_backup_store_marker")
    return path
