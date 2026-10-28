"""Bridge only. AES, AAD, DEK handling and HMAC implementation belong to Module A."""
import importlib
import os
from pathlib import Path
import re


class CryptoUnavailable(Exception):
    pass


def checked_result(method, result, arguments=()):
    """Reject missing/malformed data; this validates the contract, not cryptographic tags."""
    key = lambda value: isinstance(value, bytes) and len(value) == 32
    valid = False
    if method == "blind_index":
        valid = key(result)
    elif method == "unwrap_many":
        valid = isinstance(result, list) and len(result) == len(arguments[1]) and all(key(v) for v in result)
    elif method == "decrypt_field":
        valid = isinstance(result, str)
    elif method == "encrypt_field":
        valid = isinstance(result, bytes) and len(result) >= 29 and result[0] == 1
    elif method == "new_record_keys":
        valid = isinstance(result, dict) and set(result) == {"pii", "fin"} and all(
            isinstance(pair, (tuple, list)) and len(pair) == 2 and key(pair[0]) and isinstance(pair[1], str)
            and re.fullmatch(r"vault:v[1-9][0-9]*:.+", pair[1]) for pair in result.values())
    if not valid:
        raise CryptoUnavailable("Invalid toolkit result")
    return result


class ToolkitAdapter:
    METHODS = ("blind_index", "unwrap_many", "decrypt_field", "encrypt_field", "new_record_keys")

    def __init__(self, settings):
        if settings.crypto_factory not in {"dprcrypto:public-v1", "dprcrypto:create_service"}:
            raise ValueError("Only the reviewed Module A public API may be loaded")
        if not settings.openbao_addr.startswith("https://") or not settings.openbao_token or not Path(settings.openbao_cacert).is_file():
            raise CryptoUnavailable("Verified OpenBao identity/CA required")
        try:
            # A reads process env, validates workload identity and verifies TLS.
            # Never mutate global env per request or inject a literal token into A.
            if os.environ.get("OPENBAO_ADDR") != settings.openbao_addr or os.environ.get("OPENBAO_CACERT") != settings.openbao_cacert:
                raise ValueError()
            self.toolkit = importlib.import_module("dprcrypto")
            self.client = self.toolkit.OpenBaoClient()
            self.keys = self.toolkit.KeyManager(self.client, cache_ttl=0, max_entries=0)
            self.index = self.toolkit.BlindIndexer(self.client, key_version=1)
        except Exception:
            raise CryptoUnavailable("Module A dprcrypto service interface unavailable") from None

    def __getattr__(self, name):
        if name not in self.METHODS:
            raise AttributeError(name)
        def operation(*args, **kwargs):
            try:
                if name == "blind_index":
                    result = self.index.digest(*args)
                elif name == "unwrap_many":
                    result = self.keys.unwrap_many({"pii": "pii-kek", "fin": "finance-kek"}[args[0]], args[1])
                elif name in {"decrypt_field", "encrypt_field"}:
                    result = getattr(self.toolkit, "decrypt" if name == "decrypt_field" else "encrypt")(*args, **kwargs)
                else:
                    keys = self.keys.create_record_keys()
                    result = {"pii": (keys.pii.dek, keys.pii.wrapped), "fin": (keys.finance.dek, keys.finance.wrapped)}
                return checked_result(name, result, args)
            except Exception:
                raise CryptoUnavailable("Protected operation failed") from None
        return operation

    def close(self):
        self.keys.close()
        self.client.close()
