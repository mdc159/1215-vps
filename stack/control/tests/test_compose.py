"""Tests for compose.py."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from control import compose


def test_build_command_composes_all_files():
    cmd = compose.build_command(
        project="localai",
        compose_files=[Path("/a.yml"), Path("/b.yml")],
        subcommand=["up", "-d"],
    )
    assert cmd == [
        "docker",
        "compose",
        "-p",
        "localai",
        "-f",
        "/a.yml",
        "-f",
        "/b.yml",
        "up",
        "-d",
    ]


def test_build_command_requires_at_least_one_compose_file():
    with pytest.raises(ValueError, match="at least one"):
        compose.build_command(
            project="localai",
            compose_files=[],
            subcommand=["ps"],
        )


def test_run_invokes_subprocess_with_built_command(mocker):
    mock_run = mocker.patch("control.compose.subprocess.run")
    mock_run.return_value = MagicMock(returncode=0)

    compose.run(
        project="localai",
        compose_files=[Path("/a.yml")],
        subcommand=["ps"],
    )

    args, kwargs = mock_run.call_args
    assert args[0] == [
        "docker",
        "compose",
        "-p",
        "localai",
        "-f",
        "/a.yml",
        "ps",
    ]
    assert kwargs["capture_output"] is False
    assert kwargs["text"] is True


def test_run_raises_on_nonzero_exit(mocker):
    mocker.patch(
        "control.compose.subprocess.run",
        return_value=MagicMock(returncode=2, stdout="", stderr="boom"),
    )

    with pytest.raises(compose.ComposeError, match="exit 2"):
        compose.run(
            project="localai",
            compose_files=[Path("/a.yml")],
            subcommand=["up"],
            capture=True,
        )
