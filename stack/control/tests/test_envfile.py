"""Tests for .env parsing and rendering."""
from pathlib import Path

import pytest

from control import envfile


def test_parse_simple_key_value(tmp_path: Path):
    p = tmp_path / ".env"
    p.write_text("FOO=bar\nBAZ=qux\n")
    assert envfile.parse(p) == {"FOO": "bar", "BAZ": "qux"}


def test_parse_ignores_comments_and_blank_lines(tmp_path: Path):
    p = tmp_path / ".env"
    p.write_text(
        "# comment\n"
        "\n"
        "FOO=bar\n"
        "  # indented comment\n"
        "BAZ=qux\n"
    )
    assert envfile.parse(p) == {"FOO": "bar", "BAZ": "qux"}


def test_parse_allows_equals_in_values(tmp_path: Path):
    p = tmp_path / ".env"
    p.write_text("URI=postgres://u:p@h:5432/db?sslmode=require\n")
    assert envfile.parse(p)["URI"] == "postgres://u:p@h:5432/db?sslmode=require"


def test_parse_strips_surrounding_double_quotes(tmp_path: Path):
    p = tmp_path / ".env"
    p.write_text('FOO="bar with spaces"\n')
    assert envfile.parse(p) == {"FOO": "bar with spaces"}


def test_parse_strips_surrounding_single_quotes(tmp_path: Path):
    p = tmp_path / ".env"
    p.write_text("FOO='bar'\n")
    assert envfile.parse(p) == {"FOO": "bar"}


def test_parse_missing_file_returns_empty_dict(tmp_path: Path):
    assert envfile.parse(tmp_path / "does-not-exist") == {}


def test_parse_rejects_malformed_line(tmp_path: Path):
    p = tmp_path / ".env"
    p.write_text("FOO=bar\nnot-a-valid-line\n")
    with pytest.raises(ValueError, match="line 2"):
        envfile.parse(p)
