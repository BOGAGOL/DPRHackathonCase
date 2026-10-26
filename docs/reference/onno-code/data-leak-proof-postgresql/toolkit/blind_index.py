import hashlib
import hmac
import re
import unicodedata


def normalize_email(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def normalize_phone(value: str) -> str:
    digits = re.sub(r"[^0-9+]", "", value.strip())
    if digits.startswith("0"):
        digits = "+62" + digits[1:]
    return digits


def blind_index(domain: str, normalized_value: str, key: bytes) -> bytes:
    if len(key) < 32:
        raise ValueError("blind_index_key_too_short")
    message = f"blind-index:v1:{domain}:{normalized_value}".encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).digest()

