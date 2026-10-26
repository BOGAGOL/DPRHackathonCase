"""Small administration API: verified HTTPS, no redirects, no response-body logs."""

import json
import os
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener


class BaoError(RuntimeError):
    def __init__(self, status: int = 0):
        self.status = status
        super().__init__(f"OpenBao request failed (HTTP {status}; response withheld)")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class BaoAPI:
    def __init__(self, address: str, ca_file: str):
        parsed = urlsplit(address)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
            raise ValueError("OPENBAO_ADDR must be an HTTPS origin without credentials")
        self.address = address.rstrip("/")
        context = ssl.create_default_context(cafile=ca_file)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context), NoRedirect())

    def request(self, path: str, payload: dict | None = None, *, token: str | None = None) -> dict:
        if not path.startswith("/") or path.startswith("//") or ".." in path:
            raise ValueError("Invalid API path")
        headers = {"Content-Type": "application/json", "X-Vault-Request": "true"}
        if token:
            headers["X-Vault-Token"] = token
        request = Request(self.address + "/v1" + path,
                          data=None if payload is None else json.dumps(payload).encode(), headers=headers)
        try:
            with self.opener.open(request, timeout=10) as response:
                data = response.read()
                return json.loads(data) if data else {}
        except HTTPError as error:
            status = error.code
            error.close()
            raise BaoError(status) from None
        except (URLError, OSError, ValueError):
            raise BaoError() from None


def from_environment() -> BaoAPI:
    return BaoAPI(os.environ["OPENBAO_ADDR"], os.environ["OPENBAO_CACERT"])
