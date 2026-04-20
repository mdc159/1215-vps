"""Tests for secret generation."""
import re

import pytest

from control import secrets


def test_generate_hex_returns_lowercase_hex_of_requested_length():
    value = secrets.generate_hex(32)
    assert re.fullmatch(r"[0-9a-f]{64}", value), f"unexpected format: {value!r}"


def test_generate_hex_different_each_call():
    a = secrets.generate_hex(32)
    b = secrets.generate_hex(32)
    assert a != b, "two calls produced the same hex — RNG is broken"


def test_generate_hex_rejects_non_positive_length():
    with pytest.raises(ValueError):
        secrets.generate_hex(0)
    with pytest.raises(ValueError):
        secrets.generate_hex(-1)
