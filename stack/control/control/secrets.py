"""Secret generation primitives.

Pure functions — no filesystem or env reads. Consumed by envfile.py
when populating missing `.env` keys.
"""
import secrets as _stdlib_secrets
import string


def generate_hex(nbytes: int) -> str:
    """Return a lowercase hex string representing `nbytes` random bytes.

    The returned string has length `2 * nbytes`.
    """
    if nbytes <= 0:
        raise ValueError(f"nbytes must be positive, got {nbytes!r}")
    return _stdlib_secrets.token_hex(nbytes)


def generate_alnum(length: int) -> str:
    """Return a random alphanumeric string of exactly `length` characters."""
    if length <= 0:
        raise ValueError(f"length must be positive, got {length!r}")
    alphabet = string.ascii_letters + string.digits
    return "".join(_stdlib_secrets.choice(alphabet) for _ in range(length))


def populate_missing(
    existing: dict[str, str],
    required: dict[str, tuple[str, int]],
) -> dict[str, str]:
    """Return a new dict where every key in `required` has a non-empty value."""
    out = dict(existing)
    for key, (strategy, n) in required.items():
        if out.get(key):
            continue
        if strategy == "hex":
            out[key] = generate_hex(n)
        elif strategy == "alnum":
            out[key] = generate_alnum(n)
        else:
            raise ValueError(f"unknown strategy {strategy!r} for key {key!r}")
    return out
