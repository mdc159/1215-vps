"""Secret generation primitives.

Pure functions — no filesystem or env reads. Consumed by envfile.py
when populating missing `.env` keys.
"""
import secrets as _stdlib_secrets


def generate_hex(nbytes: int) -> str:
    """Return a lowercase hex string representing `nbytes` random bytes.

    The returned string has length `2 * nbytes`.
    """
    if nbytes <= 0:
        raise ValueError(f"nbytes must be positive, got {nbytes!r}")
    return _stdlib_secrets.token_hex(nbytes)
