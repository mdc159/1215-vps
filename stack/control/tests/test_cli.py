"""Tests for the CLI surface."""
from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from control import cli


def test_check_exits_zero_when_env_and_example_exist(tmp_path: Path):
    example = tmp_path / "env" / ".env.example"
    example.parent.mkdir()
    example.write_text("SECRET=\nKEEP=static\n")

    runner = CliRunner()
    result = runner.invoke(
        cli.main,
        ["--env-dir", str(tmp_path / "env"), "check"],
    )
    assert result.exit_code == 0, result.output


def test_check_exits_nonzero_when_example_missing(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(
        cli.main,
        ["--env-dir", str(tmp_path / "env"), "check"],
    )
    assert result.exit_code != 0
    assert ".env.example" in result.output


def test_check_reports_missing_required_keys(tmp_path: Path):
    example = tmp_path / "env" / ".env.example"
    example.parent.mkdir()
    example.write_text("MY_SECRET=\n")

    env = tmp_path / "env" / ".env"
    env.write_text("MY_SECRET=\n")

    runner = CliRunner()
    result = runner.invoke(
        cli.main,
        ["--env-dir", str(tmp_path / "env"), "check", "--no-generate"],
    )
    assert result.exit_code != 0
    assert "POSTGRES_PASSWORD" in result.output
