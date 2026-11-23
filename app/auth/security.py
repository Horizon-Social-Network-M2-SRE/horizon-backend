"""Password hashing with argon2 (shared by register and login)."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()

# Verified against when the email is unknown, so a missing account takes as long as a wrong password.
_DUMMY_HASH = _hasher.hash("not-a-real-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    # A missing or empty hash is checked against the dummy one (same timing) but never succeeds,
    # even when the password happens to match the dummy.
    has_hash = bool(password_hash)
    try:
        matches = _hasher.verify(password_hash if has_hash else _DUMMY_HASH, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return matches and has_hash
