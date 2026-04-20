#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Codex PRP executor — runs a PRP (Prompt-Response Plan) through Codex CLI.

Reads a PRP markdown file, extracts acceptance criteria and test plan,
constructs a structured prompt, and executes via codex exec.

Usage:
    uv run codex_prp_executor.py PRPs/add-auth.md -m gpt-5.3-codex
    uv run codex_prp_executor.py PRPs/refactor-db.md

Output files (all in /tmp/):
    codex-prp-{name}-output.log   — full stdout+stderr from codex exec
    codex-prp-{name}-done.json    — completion flag
    codex-prp-{name}-report.json  — structured report (files changed, criteria met, tests)
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


def extract_prp_sections(content: str) -> dict:
    """Extract key sections from a PRP markdown file."""
    sections = {}
    current_section = None
    current_lines: list[str] = []

    for line in content.splitlines():
        if line.startswith("## "):
            if current_section:
                sections[current_section] = "\n".join(current_lines).strip()
            current_section = line[3:].strip()
            current_lines = []
        elif current_section:
            current_lines.append(line)

    if current_section:
        sections[current_section] = "\n".join(current_lines).strip()

    return sections


def build_prp_prompt(prp_path: str, prp_content: str, sections: dict,
                     report_file: str) -> str:
    """Construct the Codex prompt from PRP content."""
    # Extract name from filename
    name = Path(prp_path).stem

    prompt = f"""You are executing a PRP (Prompt-Response Plan) implementation task.

## PRP: {name}

{prp_content}

## Execution Instructions

1. Read the full PRP above carefully
2. Implement ALL changes described in the PRP
3. After implementation, verify against the acceptance criteria
4. Run any tests described in the Test Plan section

## Acceptance Criteria to Verify
{sections.get('Acceptance Criteria', sections.get('acceptance criteria', 'No acceptance criteria found — implement as described.'))}

## Test Plan
{sections.get('Test Plan', sections.get('test plan', 'No test plan found — verify manually.'))}

## Output Requirements
After completing the task, write a JSON report to {report_file} with this structure:
{{
    "prp": "{name}",
    "status": "success" or "partial" or "failed",
    "files_changed": [
        {{"path": "relative/path", "action": "created|modified|deleted", "description": "what changed"}}
    ],
    "acceptance_criteria": [
        {{"criterion": "description", "met": true/false, "notes": "details"}}
    ],
    "tests_run": [
        {{"test": "description", "passed": true/false, "output": "brief output"}}
    ],
    "issues": ["any issues or follow-ups"],
    "summary": "one-line summary of what was accomplished"
}}
"""
    return prompt


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Execute a PRP via Codex CLI")
    parser.add_argument("prp_path", help="Path to PRP markdown file")
    parser.add_argument("-m", "--model", default="gpt-5.3-codex", help="Codex model to use")
    args = parser.parse_args()

    prp_path = Path(args.prp_path)
    if not prp_path.exists():
        print(f"[codex-prp] PRP file not found: {prp_path}")
        sys.exit(1)

    prp_content = prp_path.read_text(encoding="utf-8")
    sections = extract_prp_sections(prp_content)

    # Derive name slug from filename
    name = re.sub(r'[^a-z0-9]', '-', prp_path.stem.lower())
    name = re.sub(r'-+', '-', name).strip('-')

    tmpdir = _posix_path(tempfile.gettempdir())
    prefix = f"{tmpdir}/codex-prp-{name}"
    output_log = f"{prefix}-output.log"
    done_file = f"{prefix}-done.json"
    report_file = f"{prefix}-report.json"

    prompt = build_prp_prompt(str(prp_path), prp_content, sections, report_file)

    print(f"[codex-prp] Executing PRP: {prp_path.name}")
    print(f"[codex-prp] Model: {args.model}")
    print(f"[codex-prp] Sections found: {list(sections.keys())}")

    start = time.time()

    try:
        with open(output_log, "w") as log:
            result = subprocess.run(
                [
                    "codex", "exec",
                    "--dangerously-bypass-approvals-and-sandbox",
                    "-c", f'model="{args.model}"',
                    prompt,
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=600,
            )
        duration = round(time.time() - start, 1)

        # Try to read the report Codex wrote
        report = None
        if Path(report_file).exists():
            try:
                report = json.loads(Path(report_file).read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass

        done = {
            "status": "success" if result.returncode == 0 else "error",
            "exit_code": result.returncode,
            "duration_seconds": duration,
            "model": args.model,
            "prp": str(prp_path),
            "sections_found": list(sections.keys()),
            "report_file": report_file if report else None,
            "output_log": output_log,
            "validation": {
                "report_written": report is not None,
                "criteria_count": len(report.get("acceptance_criteria", [])) if report else 0,
                "tests_count": len(report.get("tests_run", [])) if report else 0,
            } if report else None,
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

    Path(done_file).write_text(json.dumps(done, indent=2) + "\n", encoding="utf-8")
    print(f"[codex-prp] Done: {json.dumps(done)}")


if __name__ == "__main__":
    main()
