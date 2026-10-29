"""HTTPS-only API launcher. Run from repository root in PowerShell."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app/backend"))
sys.path.insert(0, str(ROOT / "toolkit"))
import uvicorn
from service_app.token_source import load_runtime_token


def main():
    cert, key = os.environ.get("TLS_CERT_FILE"), os.environ.get("TLS_KEY_FILE")
    if not cert or not key or not Path(cert).is_file() or not Path(key).is_file():
        raise ValueError("Set TLS_CERT_FILE and TLS_KEY_FILE from Module A; HTTP fallback is forbidden")
    load_runtime_token()
    uvicorn.run("service_app.main:create_app", factory=True, host="127.0.0.1", port=int(os.getenv("API_PORT", "8100")),
                ssl_certfile=cert, ssl_keyfile=key, access_log=False, proxy_headers=False, server_header=False)


if __name__ == "__main__":
    main()
