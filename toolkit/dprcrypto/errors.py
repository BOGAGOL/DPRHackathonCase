"""Safe public exceptions: messages never include input, keys, or HTTP responses."""


class CryptoError(Exception):
    """Invalid encryption input or unavailable cryptographic operation."""


class DecryptionError(CryptoError):
    """Unsupported/corrupt blob, wrong key/AAD, or invalid decrypted UTF-8."""


class OpenBaoError(CryptoError):
    """Transport, authorization, or malformed Transit response."""

    def __init__(self, status: int = 0):
        self.status = status
        super().__init__(f"Key service unavailable (HTTP {status}; details withheld)")
