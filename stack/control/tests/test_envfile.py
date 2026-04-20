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


def test_parse_ignores_inline_comments_for_unquoted_values(tmp_path: Path):
    p = tmp_path / ".env"
    p.write_text("FOO=   # generated later\nBAR=qux # note\n")
    assert envfile.parse(p) == {"FOO": "", "BAR": "qux"}


def test_parse_missing_file_returns_empty_dict(tmp_path: Path):
    assert envfile.parse(tmp_path / "does-not-exist") == {}


def test_parse_rejects_malformed_line(tmp_path: Path):
    p = tmp_path / ".env"
    p.write_text("FOO=bar\nnot-a-valid-line\n")
    with pytest.raises(ValueError, match="line 2"):
        envfile.parse(p)


def test_render_preserves_template_comments_and_order(tmp_path: Path):
    template = tmp_path / ".env.example"
    template.write_text(
        "# Supabase\n"
        "POSTGRES_PASSWORD=\n"
        "JWT_SECRET=\n"
        "\n"
        "# Neo4j\n"
        "NEO4J_AUTH=\n"
    )
    values = {
        "POSTGRES_PASSWORD": "abc",
        "JWT_SECRET": "def",
        "NEO4J_AUTH": "neo4j/pw",
    }
    rendered = envfile.render(template, values)
    assert rendered == (
        "# Supabase\n"
        "POSTGRES_PASSWORD=abc\n"
        "JWT_SECRET=def\n"
        "\n"
        "# Neo4j\n"
        "NEO4J_AUTH=neo4j/pw\n"
    )


def test_render_appends_unknown_keys_at_end(tmp_path: Path):
    template = tmp_path / ".env.example"
    template.write_text("FOO=\n")
    rendered = envfile.render(template, {"FOO": "1", "EXTRA": "2"})
    assert rendered.endswith("EXTRA=2\n")
    assert "FOO=1" in rendered


def test_render_leaves_template_missing_key_blank(tmp_path: Path):
    template = tmp_path / ".env.example"
    template.write_text("FOO=\nBAR=\n")
    rendered = envfile.render(template, {"FOO": "x"})
    assert "FOO=x\n" in rendered
    assert "BAR=\n" in rendered


def test_compose_honcho_uri_builds_correct_format():
    uri = envfile.compose_honcho_uri(password="s3cret")
    assert uri == "postgresql+psycopg://honcho_app:s3cret@db:5432/honcho"


def test_compose_honcho_uri_rejects_empty_password():
    with pytest.raises(ValueError, match="password required"):
        envfile.compose_honcho_uri(password="")


def test_compose_honcho_uri_url_encodes_special_chars():
    uri = envfile.compose_honcho_uri(password="p@ss:word")
    assert uri == "postgresql+psycopg://honcho_app:p%40ss%3Aword@db:5432/honcho"
