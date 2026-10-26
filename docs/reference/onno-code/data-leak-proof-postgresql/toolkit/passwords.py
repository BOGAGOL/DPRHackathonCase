from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError


class PasswordService:
    def __init__(self, pepper: str = ""):
        self.hasher = PasswordHasher()
        self.pepper = pepper

    def hash(self, password: str) -> str:
        return self.hasher.hash(password + self.pepper)

    def verify(self, stored_hash: str, password: str) -> tuple[bool, str | None]:
        try:
            valid = self.hasher.verify(stored_hash, password + self.pepper)
        except VerifyMismatchError:
            return False, None
        replacement = self.hash(password) if self.hasher.check_needs_rehash(stored_hash) else None
        return valid, replacement

