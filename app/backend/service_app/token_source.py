"""Read the operator-installed, private token sink once at API startup."""
import os
from pathlib import Path
import stat


def load_runtime_token():
    configured = os.environ.get("DPR_APP_TOKEN_FILE")
    if not configured:
        return
    path = Path(configured)
    if path != Path("/run/dpr-service-app/svc-app.token"):
        raise ValueError("Unexpected application token sink")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_size > 4097
                or info.st_uid != 0 or info.st_gid != os.getegid()
                or stat.S_IMODE(info.st_mode) != 0o640):
            raise ValueError("Application token sink must be root-owned and private")
        with os.fdopen(descriptor, "r", encoding="ascii", closefd=False) as stream:
            value = stream.read(4098).removesuffix("\n")
        if not value or len(value) > 4096 or any(c.isspace() for c in value):
            raise ValueError("Invalid application token sink")
        os.environ["OPENBAO_TOKEN"] = value
    finally:
        os.close(descriptor)
