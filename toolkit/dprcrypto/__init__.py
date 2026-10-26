"""DPR protection contract v1; all keys and workload credentials stay out of logs."""

from .bidx import BlindIndexer, index_message, normalize
from .codec import build_aad, decrypt, encrypt
from .errors import CryptoError, DecryptionError, OpenBaoError
from .masking import mask_account, mask_email, mask_name, mask_nik, mask_phone
from .keys import KeyManager, RecordKeys, WrappedDEK
from .openbao import OpenBaoClient

__all__ = [
    "BlindIndexer", "CryptoError", "DecryptionError", "OpenBaoError", "build_aad",
    "decrypt", "encrypt", "index_message", "normalize", "mask_account", "mask_email",
    "mask_name", "mask_nik", "mask_phone",
    "KeyManager", "OpenBaoClient", "RecordKeys", "WrappedDEK",
]
