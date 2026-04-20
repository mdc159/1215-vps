#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""OpenCode task executor — runs an OpenCode CLI task non-interactively and writes results.

Designed to be called inside a forked terminal by the opencode-delegator agent.

Usage:
    uv run opencode_task_executor.py /tmp/prompt.txt -n my-task -m openai/gpt-5.3-codex
    uv run opencode_task_executor.py /tmp/prompt.txt -n my-task --agent hephaestus
    uv run opencode_task_executor.py - -n my-task  # reads prompt from stdin

## STABLE CONTRACT — do not break without updating all callers
##
## Callers:
##   - .claude/agents/opencode-delegator.md (polls done.json, reads summary)
##
## CLI interface (stable):
##   positional: prompt_file  — path to prompt text file, or "-" for stdin
##   -n / --name             — task slug, used in all output filenames
##   -m / --model            — OpenCode model in provider/model format
##                              (default: openai/gpt-5.3-codex)
##   --agent                 — oh-my-opencode agent name (overrides -m)
##   --dir                   — working directory for opencode (default: current dir)
##   --fallback-models       — comma-separated fallback models on failure
##   --workflow / -w         — workflow name from workflow_cascades.json
##                              (overrides --model, --agent, --fallback-models)
##   --timeout               — max seconds per model attempt (default: 600)
##                              (auto-set by --workflow from cascade config)
##   --retry-delay           — seconds between retries (default: 10)
##   --max-retries           — max retries per model (default: 1)
##
## Output files (stable paths — callers poll/read these):
##   /tmp/opencode-task-{name}-output.log  — full stdout+stderr
##   /tmp/opencode-task-{name}-done.json   — completion flag (callers poll this)
##   /tmp/opencode-task-{name}-summary.md  — review/summary (written by OpenCode via prompt)
##
## done.json schema (stable — callers parse these keys):
##   {
##     "status": "success" | "error" | "timeout",
##     "exit_code": int,
##     "duration_seconds": float,
##     "model": str,
##     "agent": str | null,
##     "retries_used": int,
##     "output_log": str,
##     "summary_file": str,
##     "error_type": str,
##     "message": str
##   }
##
## COST RULE: Never use opencode/claude-* models (Anthropic API-billed).
## For Claude, fork to Toad (Claude Code, Max Plan).
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

# Models that MUST NOT be used — they incur Anthropic API costs.
BLOCKED_MODELS = {
    "opencode/claude-opus-4-6",
    "opencode/claude-opus-4-5",
    "opencode/claude-sonnet-4-5",
    "opencode/claude-sonnet-4",
    "opencode/claude-haiku-4-5",
    "opencode/claude-3-5-haiku",
}


def run_opencode(prompt: str, model: str, name: str,
                 agent: str | None = None,
                 work_dir: str | None = None,
                 fallback_models: list[str] | None = None,
                 retry_delay: int = 10, max_retries: int = 1,
                 timeout: int = 600) -> dict:
    """Run OpenCode CLI and return completion info."""
    tmpdir = _posix_path(tempfile.gettempdir())
    prefix = f"{tmpdir}/opencode-task-{name}"
    output_log = f"{prefix}-output.log"
    summary_file = f"{prefix}-summary.md"

    models_to_try = [model] + (fallback_models or [])
    retries_used = 0
    last_error = None
    effective_model = model

    for i, try_model in enumerate(models_to_try):
        # Block Anthropic models
        if try_model in BLOCKED_MODELS:
            print(f"[opencode-executor] BLOCKED: {try_model} (Anthropic API-billed). Skipping.")
            last_error = "BLOCKED_MODEL"
            continue

        for attempt in range(max_retries + 1):
            if i > 0 or attempt > 0:
                retries_used += 1
                wait = retry_delay * (attempt + 1)
                print(f"[opencode-executor] Retry {retries_used}: model={try_model}, waiting {wait}s...")
                time.sleep(wait)

            # Build command (OpenCode auto-approves tool use — no dangerous/yolo
            # flag needed. `--dangerously-skip-permissions` does not exist in
            # OpenCode CLI and will cause exit 1. See cookbook/opencode-cli.md.)
            cmd = ["opencode", "run", prompt, "--format", "default"]

            # --agent overrides -m for the primary attempt
            if agent and i == 0:
                cmd.extend(["--agent", agent])
                print(f"[opencode-executor] Running: agent={agent}, attempt={attempt + 1}")
            else:
                cmd.extend(["-m", try_model])
                print(f"[opencode-executor] Running: model={try_model}, attempt={attempt + 1}")

            # For non-OpenAI models (Groq, Antigravity), disable thinking to avoid
            # tool-calling errors from oh-my-opencode's isGptModel() adding unsupported
            # thinking config. OpenAI models keep their default variant.
            if not try_model.startswith("openai/"):
                cmd.extend(["--variant", "minimal"])

            if work_dir:
                cmd.extend(["--dir", work_dir])

            effective_model = try_model
            start = time.time()

            try:
                # Write diagnostic header, then append OpenCode output
                mode = "w" if (i == 0 and attempt == 0) else "a"
                with open(output_log, mode) as log:
                    log.write(f"--- [opencode-executor] model={try_model} agent={agent if i == 0 else None} "
                              f"attempt={attempt + 1} timeout={timeout}s ---\n")
                    log.flush()
                    result = subprocess.run(
                        cmd,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        timeout=timeout,
                    )
                duration = round(time.time() - start, 1)

                if result.returncode == 0:
                    return {
                        "status": "success",
                        "exit_code": 0,
                        "duration_seconds": duration,
                        "model": effective_model,
                        "agent": agent if i == 0 else None,
                        "retries_used": retries_used,
                        "output_log": output_log,
                        "summary_file": summary_file,
                    }

                # Check output for rate limit / quota errors
                log_content = Path(output_log).read_text(encoding="utf-8", errors="replace")

                if "rate limit" in log_content.lower() or "429" in log_content:
                    last_error = "RATE_LIMITED"
                    print(f"[opencode-executor] Rate limited on {try_model}")
                    continue
                elif "quota" in log_content.lower() or "insufficient" in log_content.lower():
                    last_error = "QUOTA_EXHAUSTED"
                    print(f"[opencode-executor] Quota exhausted on {try_model}")
                    continue

                # Non-rate-limit error — don't retry same model
                return {
                    "status": "error",
                    "exit_code": result.returncode,
                    "duration_seconds": duration,
                    "model": effective_model,
                    "agent": agent if i == 0 else None,
                    "retries_used": retries_used,
                    "error_type": "EXEC_FAILED",
                    "output_log": output_log,
                }

            except subprocess.TimeoutExpired:
                duration = round(time.time() - start, 1)
                return {
                    "status": "timeout",
                    "exit_code": -1,
                    "duration_seconds": duration,
                    "model": effective_model,
                    "agent": agent if i == 0 else None,
                    "retries_used": retries_used,
                    "error_type": "TIMEOUT",
                    "output_log": output_log,
                }

    # All retries exhausted
    return {
        "status": "error",
        "exit_code": -1,
        "duration_seconds": 0,
        "model": model,
        "agent": agent,
        "retries_used": retries_used,
        "error_type": last_error or "ALL_RETRIES_EXHAUSTED",
        "output_log": output_log,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run an OpenCode CLI task")
    parser.add_argument("prompt_file", help="Path to prompt file, or '-' for stdin")
    parser.add_argument("-n", "--name", required=True, help="Task slug for output filenames")
    parser.add_argument("-m", "--model", default="openai/gpt-5.3-codex",
                        help="OpenCode model in provider/model format")
    parser.add_argument("--agent", default=None,
                        help="oh-my-opencode agent name (overrides -m for primary attempt)")
    parser.add_argument("--dir", default=None, help="Working directory for opencode")
    parser.add_argument("--fallback-models", default=None,
                        help="Comma-separated fallback models")
    parser.add_argument("--workflow", "-w", default=None,
                        help="Workflow name from workflow_cascades.json (overrides -m/--agent/--fallback-models)")
    parser.add_argument("--timeout", type=int, default=600,
                        help="Max seconds per model attempt (auto-set by --workflow)")
    parser.add_argument("--retry-delay", type=int, default=10,
                        help="Seconds between retries")
    parser.add_argument("--max-retries", type=int, default=1,
                        help="Max retries per model")
    parser.add_argument("--target-file", default=None,
                        help="Expected output file path — verified after completion")
    args = parser.parse_args()

    # Sanitize name slug for safe file paths
    name = re.sub(r'[^a-z0-9\-]', '-', args.name.lower())
    name = re.sub(r'-+', '-', name).strip('-')

    # Output paths — use tempfile.gettempdir() for cross-platform support
    tmpdir = _posix_path(tempfile.gettempdir())
    prefix = f"{tmpdir}/opencode-task-{name}"
    done_file = f"{prefix}-done.json"
    summary_file = f"{prefix}-summary.md"

    # Workflow cascade resolution — overrides model/agent/fallbacks from config
    if args.workflow:
        try:
            from cascade_router import get_cascade
            cascade = get_cascade(workflow=args.workflow)
            args.model = cascade["primary_model"]
            args.agent = cascade.get("primary_agent") or args.agent
            args.fallback_models = ",".join(cascade["fallback_models"]) if cascade["fallback_models"] else args.fallback_models
            args.timeout = cascade.get("timeout", args.timeout)
            print(f"[opencode-executor] Workflow: {cascade['workflow']}")
            print(f"[opencode-executor] Timeout: {args.timeout}s")
            print(f"[opencode-executor] Cascade: {cascade['primary_model']} → {' → '.join(cascade['fallback_models'])}")
        except Exception as e:
            print(f"[opencode-executor] Warning: cascade_router failed ({e}), using --model/--fallback-models")

    # Block Anthropic models early
    if args.model in BLOCKED_MODELS:
        print(f"[opencode-executor] BLOCKED: {args.model} is an Anthropic model (API-billed).")
        print(f"[opencode-executor] Use Toad (Claude Code) for Anthropic models, or pick a different model.")
        done = {
            "status": "error",
            "exit_code": -1,
            "duration_seconds": 0,
            "error_type": "BLOCKED_MODEL",
            "message": f"{args.model} blocked — Anthropic API costs. Use Toad for Claude models.",
        }
        Path(done_file).write_text(json.dumps(done, indent=2) + "\n", encoding="utf-8")
        return

    # Read prompt
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
        print(f"[opencode-executor] Failed to read prompt: {e}")
        return

    # Append output instructions to prompt
    full_prompt = f"""{prompt}

## Output Requirements
After completing the task, write a concise summary of your work to {summary_file}.
Include: files changed, what was done, any issues found."""

    print(f"[opencode-executor] Starting task: {args.name}")
    print(f"[opencode-executor] Model: {args.model}")
    if args.agent:
        print(f"[opencode-executor] Agent: {args.agent}")
    print(f"[opencode-executor] Output: {prefix}-output.log")

    fallbacks = args.fallback_models.split(",") if args.fallback_models else []

    try:
        done = run_opencode(
            prompt=full_prompt,
            model=args.model,
            name=name,
            agent=args.agent,
            work_dir=args.dir,
            fallback_models=fallbacks,
            retry_delay=args.retry_delay,
            max_retries=args.max_retries,
            timeout=args.timeout,
        )
    except FileNotFoundError:
        done = {
            "status": "error",
            "exit_code": -1,
            "duration_seconds": 0,
            "error_type": "CLI_NOT_FOUND",
            "message": "opencode CLI not found. Install: npm install -g opencode-ai",
        }
    except Exception as e:
        done = {
            "status": "error",
            "exit_code": -1,
            "duration_seconds": 0,
            "error_type": type(e).__name__,
            "message": str(e),
        }

    # Content verification — check if the model wrote the expected output file
    if args.target_file and done.get("status") == "success":
        target = Path(args.target_file)
        if target.exists() and target.stat().st_size > 100:
            done["content_verified"] = True
            print(f"[opencode-executor] Target file verified: {args.target_file} ({target.stat().st_size} bytes)")
        else:
            done["status"] = "partial"
            done["content_verified"] = False
            reason = "not found" if not target.exists() else f"too small ({target.stat().st_size} bytes)"
            done["content_message"] = f"Target file {reason}: {args.target_file}"
            print(f"[opencode-executor] WARNING: Target file {reason}: {args.target_file}")

    # Write done flag
    Path(done_file).write_text(json.dumps(done, indent=2) + "\n", encoding="utf-8")
    print(f"[opencode-executor] Done: {json.dumps(done)}")


if __name__ == "__main__":
    main()
