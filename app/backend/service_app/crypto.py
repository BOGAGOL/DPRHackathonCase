"""Bridge only. AES, AAD, DEK handling and HMAC implementation belong to Module A."""
import importlib
from pathlib import Path
import re
import ssl


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
        module, separator, name = settings.crypto_factory.partition(":")
        if not separator or not (module == "dprcrypto" or module.startswith("dprcrypto.")):
            raise ValueError("Only the Module A dprcrypto factory may be loaded")
        if not settings.openbao_addr.startswith("https://") or not settings.openbao_token or not Path(settings.openbao_cacert).is_file():
            raise CryptoUnavailable("Verified OpenBao identity/CA required")
        context = ssl.create_default_context(cafile=settings.openbao_cacert)
        try:
            factory = getattr(importlib.import_module(module), name)
            self.driver = factory(openbao_addr=settings.openbao_addr, token=settings.openbao_token, ssl_context=context)
            if not all(callable(getattr(self.driver, method, None)) for method in self.METHODS):
                raise TypeError()
        except Exception:
            raise CryptoUnavailable("Module A dprcrypto service interface unavailable") from None

    def __getattr__(self, name):
        if name not in self.METHODS:
            raise AttributeError(name)
        def operation(*args, **kwargs):
            try:
                return checked_result(name, getattr(self.driver, name)(*args, **kwargs), args)
            except Exception:
                raise CryptoUnavailable("Protected operation failed") from None
        return operation
