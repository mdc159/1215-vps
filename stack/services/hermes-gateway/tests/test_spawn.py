"""Unit tests for hermes_gateway.spawn.

These tests never fork a real `hermes` process — they exercise the
policy surface (`build_spawn_plan`) using a fake profile tree, a fake
workspace tree, and a fake hermes binary created as a 755 shell stub
in a tmp_path. That keeps them fast (<100ms/test) and independent of
the real /var/lib layout.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from hermes_gateway.spawn import (
    FIXED_PATH,
    PROFILE_ALLOWLIST,
    SpawnRejected,
    build_spawn_plan,
    parse_env_file,
)


# --- fixtures ---------------------------------------------------------

@pytest.fixture
def fake_tree(tmp_path: Path) -> dict[str, Path]:
    """Build a fake `/var/lib/hermes + /var/lib/paperclip/workspaces` layout
    plus an executable hermes-stub binary, all under ``tmp_path``.
    """
    profile_root = tmp_path / "hermes"
    workspace_root = tmp_path / "paperclip" / "workspaces"

    profile_dir = profile_root / "orchestrator-ceo"
    hermes_home = profile_dir / ".hermes"
    hermes_home.mkdir(parents=True)
    (hermes_home / ".env").write_text(
        "# test profile env\n"
        "OPENROUTER_API_KEY=sk-test-abc\n"
        "HERMES_CEO_CANARY=FAKE_CANARY_XYZ\n"
        "\n"
        "EMPTY_VAL=\n",
        encoding="utf-8",
    )
    (hermes_home / "config.yaml").write_text(
        "memory:\n  provider: honcho\n", encoding="utf-8"
    )

    workspace_dir = workspace_root / "orchestrator-ceo"
    workspace_dir.mkdir(parents=True)

    hermes_bin = tmp_path / "hermes-stub"
    hermes_bin.write_text("#!/usr/bin/env bash\necho stub\n", encoding="utf-8")
    hermes_bin.chmod(hermes_bin.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    return {
        "profile_root": profile_root,
        "workspace_root": workspace_root,
        "profile_dir": profile_dir,
        "hermes_home": hermes_home,
        "workspace_dir": workspace_dir,
        "hermes_bin": hermes_bin,
    }


def _happy_kwargs(fake_tree: dict[str, Path], **overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "run_id": "run-001",
        "session_id": "sess-001",
        "profile": "orchestrator-ceo",
        "prompt": "say hello",
        "profile_root": fake_tree["profile_root"],
        "workspace_root": fake_tree["workspace_root"],
        "hermes_bin": fake_tree["hermes_bin"],
    }
    defaults.update(overrides)
    return defaults


# --- parse_env_file --------------------------------------------------

def test_parse_env_file_drops_blocked_keys(tmp_path: Path) -> None:
    env_file = tmp_path / "profile.env"
    env_file.write_text(
        "# comment line\n"
        "OPENROUTER_API_KEY=sk-abc\n"
        "HERMES_HOME=/tmp/hijack\n"           # blocked
        "PATH=/usr/bin:/hijack\n"             # blocked
        "LD_PRELOAD=/tmp/evil.so\n"           # blocked
        "NORMAL=value\n"
        "\n",
        encoding="utf-8",
    )
    parsed = parse_env_file(env_file)
    assert parsed == {"OPENROUTER_API_KEY": "sk-abc", "NORMAL": "value"}


def test_parse_env_file_rejects_malformed(tmp_path: Path) -> None:
    env_file = tmp_path / "bad.env"
    env_file.write_text("NOT_AN_EQUALS\n", encoding="utf-8")
    with pytest.raises(SpawnRejected) as exc:
        parse_env_file(env_file)
    assert exc.value.reason == "bad_env_file"


def test_parse_env_file_rejects_bad_key(tmp_path: Path) -> None:
    env_file = tmp_path / "bad.env"
    env_file.write_text("BAD-KEY=1\n", encoding="utf-8")  # dash not allowed
    with pytest.raises(SpawnRejected):
        parse_env_file(env_file)


# --- build_spawn_plan: happy path -----------------------------------

def test_build_spawn_plan_happy_path(fake_tree: dict[str, Path]) -> None:
    plan = build_spawn_plan(**_happy_kwargs(fake_tree))
    assert plan.run_id == "run-001"
    assert plan.session_id == "sess-001"
    assert plan.profile == "orchestrator-ceo"
    assert plan.cwd == fake_tree["workspace_dir"]
    assert plan.hermes_home == fake_tree["hermes_home"]

    # argv shape is locked: absolute hermes + chat + the quiet/source flags
    argv = list(plan.argv)
    assert argv[0] == str(fake_tree["hermes_bin"])
    assert argv[1] == "chat"
    assert "-Q" in argv
    assert "-q" in argv
    # -q MUST be followed by the exact prompt
    assert argv[argv.index("-q") + 1] == "say hello"
    assert "--pass-session-id" in argv
    # --source tool keeps gateway runs out of user session lists
    assert argv[argv.index("--source") + 1] == "tool"

    env = plan.env
    assert env["PATH"] == FIXED_PATH
    assert env["HERMES_HOME"] == str(fake_tree["hermes_home"])
    assert env["HOME"] == str(fake_tree["profile_dir"])
    assert env["OPENROUTER_API_KEY"] == "sk-test-abc"
    assert env["HERMES_CEO_CANARY"] == "FAKE_CANARY_XYZ"
    # LC_ALL / LANG are set to something deterministic
    assert env["LC_ALL"] == "C.UTF-8"
    # Phase G: run_id / session_id must be injected as both HERMES_* and
    # LANGFUSE_* so child processes that emit Langfuse spans share the
    # gateway's trace_id without any extra plumbing.
    assert env["HERMES_RUN_ID"] == "run-001"
    assert env["HERMES_SESSION_ID"] == "sess-001"
    assert env["LANGFUSE_TRACE_ID"] == "run-001"
    assert env["LANGFUSE_SESSION_ID"] == "sess-001"


def test_build_spawn_plan_model_override_appended(fake_tree: dict[str, Path]) -> None:
    plan = build_spawn_plan(**_happy_kwargs(fake_tree, model="openai/gpt-4o-mini"))
    argv = list(plan.argv)
    assert argv[-2:] == ["-m", "openai/gpt-4o-mini"]


# --- build_spawn_plan: policy rejections -----------------------------

def test_reject_unknown_profile(fake_tree: dict[str, Path]) -> None:
    with pytest.raises(SpawnRejected) as exc:
        build_spawn_plan(**_happy_kwargs(fake_tree, profile="rogue-admin"))
    assert exc.value.reason == "forbidden"
    assert "allowlist" in exc.value.detail


def test_reject_path_traversal_profile(fake_tree: dict[str, Path]) -> None:
    with pytest.raises(SpawnRejected) as exc:
        build_spawn_plan(**_happy_kwargs(fake_tree, profile="../etc"))
    # Rejected before filesystem check, as path contains '/'
    assert exc.value.reason in {"bad_request", "forbidden"}


def test_reject_empty_prompt(fake_tree: dict[str, Path]) -> None:
    with pytest.raises(SpawnRejected) as exc:
        build_spawn_plan(**_happy_kwargs(fake_tree, prompt="   "))
    assert exc.value.reason == "bad_request"


def test_reject_empty_run_id(fake_tree: dict[str, Path]) -> None:
    with pytest.raises(SpawnRejected):
        build_spawn_plan(**_happy_kwargs(fake_tree, run_id=""))


def test_reject_missing_profile_dir(fake_tree: dict[str, Path]) -> None:
    # orchestrator-ceo is in allowlist, but we point profile_root
    # somewhere the directory doesn't exist -> not_found
    bogus_root = fake_tree["profile_root"].parent / "no-such-root"
    bogus_root.mkdir()
    with pytest.raises(SpawnRejected) as exc:
        build_spawn_plan(**_happy_kwargs(fake_tree, profile_root=bogus_root))
    assert exc.value.reason == "not_found"


def test_reject_missing_env_file(fake_tree: dict[str, Path]) -> None:
    (fake_tree["hermes_home"] / ".env").unlink()
    with pytest.raises(SpawnRejected) as exc:
        build_spawn_plan(**_happy_kwargs(fake_tree))
    assert exc.value.reason == "not_found"
    assert ".env" in exc.value.detail


def test_reject_missing_workspace(fake_tree: dict[str, Path]) -> None:
    import shutil

    shutil.rmtree(fake_tree["workspace_dir"])
    with pytest.raises(SpawnRejected) as exc:
        build_spawn_plan(**_happy_kwargs(fake_tree))
    assert exc.value.reason == "not_found"


def test_reject_nonexecutable_hermes_bin(fake_tree: dict[str, Path]) -> None:
    fake_tree["hermes_bin"].chmod(0o644)
    with pytest.raises(SpawnRejected) as exc:
        build_spawn_plan(**_happy_kwargs(fake_tree))
    assert exc.value.reason == "config"


def test_reject_relative_hermes_bin(fake_tree: dict[str, Path]) -> None:
    with pytest.raises(SpawnRejected) as exc:
        build_spawn_plan(**_happy_kwargs(fake_tree, hermes_bin=Path("hermes")))
    assert exc.value.reason == "config"


def test_reject_extra_argv_overriding_query(fake_tree: dict[str, Path]) -> None:
    with pytest.raises(SpawnRejected) as exc:
        build_spawn_plan(
            **_happy_kwargs(fake_tree, extra_argv=["-q", "injected"])
        )
    assert exc.value.reason == "bad_request"


# --- invariant: canary presence test --------------------------------

def test_allowlist_contains_only_ceo() -> None:
    """Phase D lands with a single legitimate profile; adding more
    profiles later is a deliberate code change, not a config tweak.
    Guard against accidental loosening of the allowlist."""
    assert PROFILE_ALLOWLIST == frozenset({"orchestrator-ceo"})
