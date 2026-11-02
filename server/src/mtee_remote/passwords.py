"""Password hashing with Argon2id, and the rule for new passwords."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error

from mtee_remote.errors import ApiError

MIN_PASSWORD_LENGTH = 8
# Longer passwords would be accepted by the CLI but could not be sent to the login route.
MAX_PASSWORD_LENGTH = 10_000

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Return an Argon2id hash of `password` with the library defaults."""
    return _hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    """Return True only if `password` matches `stored_hash`.

    A mismatch, a malformed hash (such as the placeholder "!test") and any other Argon2
    error all give False.
    """
    try:
        return _hasher.verify(stored_hash, password)
    except (Argon2Error, ValueError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    """Return True if `stored_hash` uses older parameters; False for an invalid hash."""
    try:
        return _hasher.check_needs_rehash(stored_hash)
    except (Argon2Error, ValueError):
        return False


def check_new_password(password: str) -> None:
    """Refuse a new password that is too short or too long."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ApiError(
            "bad_request",
            f"The password must be at least {MIN_PASSWORD_LENGTH} characters long.",
        )
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ApiError(
            "bad_request",
            f"The password must be at most {MAX_PASSWORD_LENGTH} characters long.",
        )
