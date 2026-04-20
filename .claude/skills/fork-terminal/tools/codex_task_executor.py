#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Codex task executor — runs a Codex CLI task non-interactively and writes results.

Designed to be called inside a forked terminal by the codex-delegator agent.

Usage:
    uv run codex_task_executor.py /tmp/codex-task-prompt.txt -n my-task -m gpt-5.3-codex
    uv run codex_task_executor.py - -n my-task  # reads prompt from stdin

## STABLE CONTRACT — do not break without updating all callers
##
## Callers:
##   - .claude/agents/archon-task-implementor.md (polls done.json, reads summary Level 0)
##   - .claude/agents/codex-delegator.md (polls done.json, reads summary)
##   - .claude/rules/validation-loop.md (documents polling/file conventions)
##
## CLI interface (stable):
##   positional: prompt_file  — path to prompt text file, or "-" for stdin
##   -n / --name             — task slug, used in all output filenames
##   -m / --model            — Codex model (default: gpt-5.3-codex)
##
## Output files (stable paths — callers poll/read these):
##   /tmp/codex-task-{name}-output.log  — full stdout+stderr from codex exec
##   /tmp/codex-task-{name}-done.json   — completion flag (callers poll this)
##   /tmp/codex-task-{name}-summary.md  — review/summary (written by Codex via prompt)
##
## done.json schema (stable — callers parse these keys):
##   {
##     "status": "success" | "error" | "timeout",
##     "exit_code": int,
##     "duration_seconds": float,
##     "model": str,
##     "output_log": str,        # path to output log
##     "summary_file": str,      # path to summary (on success only)
##     "error_type": str,        # TIMEOUT | CLI_NOT_FOUND | exception name (on error only)
##     "message": str            # human-readable error (on error only)
##   }
##
## If you modify any of the above, you MUST update all listed callers.
"""

import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def _posix_path(p: str) -> str:
    """Normalize a path to forward slashes for use in shell commands.
    On Windows, Path() and tempfile return backslash paths which break
    bash -c redirects and tee. Always use this for shell_cmd strings."""
    return p.replace("\\", "/")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run a Codex CLI task")
    parser.add_argument("prompt_file", help="Path to prompt file, or '-' for stdin")
    parser.add_argument("-n", "--name", required=True, help="Task slug for output filenames")
    parser.add_argument("-m", "--model", default="gpt-5.3-codex", help="Codex model to use")
    args = parser.parse_args()

    # Sanitize name slug for safe file paths
    name = re.sub(r'[^a-z0-9\-]', '-', args.name.lower())
    name = re.sub(r'-+', '-', name).strip('-')

    # Output paths — use tempfile.gettempdir() for cross-platform support
    tmpdir = _posix_path(tempfile.gettempdir())
    prefix = f"{tmpdir}/codex-task-{name}"
    output_log = f"{prefix}-output.log"
    done_file = f"{prefix}-done.json"
    summary_file = f"{prefix}-summary.md"

    # Read prompt — wrapped so done.json is written on failure
    try:
        if args.prompt_file == "-":
            prompt = sys.stdin.read()
        else:
            prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    except Exception as e:
        done = {
            "status": "error",
            "exit_code": -1,
            "duration_seconds": 0,
            "error_type": "PROMPT_READ_FAILED",
            "message": str(e),
        }
        Path(done_file).write_text(json.dumps(done, indent=2) + "\n", encoding="utf-8")
        print(f"[codex-executor] Failed to read prompt: {e}")
        return

    # Append output instructions to prompt
    full_prompt = f"""{prompt}

## Output Requirements
After completing the task, write a concise summary of your work to {summary_file}.
Include: files changed, what was done, any issues found."""

    print(f"[codex-executor] Starting task: {args.name}")
    print(f"[codex-executor] Model: {args.model}")
    print(f"[codex-executor] Output: {output_log}")

    start = time.time()

    try:
        with open(output_log, "w") as log:
            result = subprocess.run(
                [
                    "codex", "exec",
                    "--dangerously-bypass-approvals-and-sandbox",
                    "-c", f'model="{args.model}"',
                    full_prompt,
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=600,  # 10 min max
            )
        duration = round(time.time() - start, 1)
        status = "success" if result.returncode == 0 else "error"

        done = {
            "status": status,
            "exit_code": result.returncode,
            "duration_seconds": duration,
            "model": args.model,
            "output_log": output_log,
            "summary_file": summary_file,
        }

    except subprocess.TimeoutExpired:
        duration = round(time.time() - start, 1)
        done = {
            "status": "timeout",
            "exit_code": -1,
            "duration_seconds": duration,
            "model": args.model,
            "error_type": "TIMEOUT",
            "output_log": output_log,
        }

    except FileNotFoundError:
        done = {
            "status": "error",
            "exit_code": -1,
            "duration_seconds": 0,
            "error_type": "CLI_NOT_FOUND",
            "message": "codex CLI not found. Install: npm install -g @openai/codex",
        }

    except Exception as e:
        duration = round(time.time() - start, 1)
        done = {
            "status": "error",
            "exit_code": -1,
            "duration_seconds": duration,
            "error_type": type(e).__name__,
            "message": str(e),
        }

    # Write done flag
    Path(done_file).write_text(json.dumps(done, indent=2) + "\n", encoding="utf-8")
    print(f"[codex-executor] Done: {json.dumps(done)}")


if __name__ == "__main__":
    main()
