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


def test_populate_missing_fills_only_absent_keys():
    existing = {"KEEP_ME": "already-set", "EMPTY_ME": ""}
    required = {
        "KEEP_ME": ("hex", 32),
        "EMPTY_ME": ("hex", 32),
        "BRAND_NEW": ("hex", 32),
    }
    out = secrets.populate_missing(existing, required)
    assert out["KEEP_ME"] == "already-set"
    assert re.fullmatch(r"[0-9a-f]{64}", out["EMPTY_ME"])
    assert re.fullmatch(r"[0-9a-f]{64}", out["BRAND_NEW"])


def test_populate_missing_supports_alnum_strategy():
    out = secrets.populate_missing({}, {"PASS": ("alnum", 24)})
    assert re.fullmatch(r"[A-Za-z0-9]{24}", out["PASS"])


def test_populate_missing_rejects_unknown_strategy():
    with pytest.raises(ValueError, match="unknown strategy"):
        secrets.populate_missing({}, {"X": ("bogus", 32)})
