"""Display masks only; authorization must run before decrypting or returning a field."""


def mask_name(value: str | None) -> str | None:
    return None if value is None else " ".join(word[:min(2, len(word) - 1)] + "***" for word in value.split())


def mask_nik(value: str | None) -> str | None:
    if value is None:
        return None
    return "*" * max(4, len(value)) if len(value) <= 8 else value[:4] + "*" * (len(value) - 8) + value[-4:]


def mask_phone(value: str | None) -> str | None:
    if value is None:
        return None
    return "*" * max(4, len(value)) if len(value) <= 8 else value[:4] + "****" + value[-4:]


def mask_email(value: str | None) -> str | None:
    if value is None:
        return None
    local, separator, domain = value.rpartition("@")
    if not separator or not local or not domain:
        return "***"
    return local[:min(2, len(local) - 1)] + "***@" + domain


def mask_account(value: str | None) -> str | None:
    if value is None:
        return None
    return "*" * max(4, len(value)) if len(value) <= 4 else "*" * (len(value) - 4) + value[-4:]
