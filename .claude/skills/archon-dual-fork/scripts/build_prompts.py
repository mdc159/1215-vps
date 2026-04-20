#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Build IMPL and REVIEW prompt files for one Archon task.

Input: a JSON file containing the Archon task record (as returned by
`find_tasks(task_id=...)`). The orchestrator is responsible for pulling
this from Archon MCP and writing it to disk before invoking this script.

Output: two prompt files in $TMPDIR:
  - codex-impl-{slug}-prompt.txt
  - codex-review-{slug}-prompt.txt

Usage:
  uv run build_prompts.py --task-json /tmp/task-<id>.json [--attempt N]
      [--remediation-file /tmp/remediation-<slug>.md] [--tmpdir DIR]

The orchestrator is the sole Archon writer. This script only reads
input JSON and writes prompt files — it never calls Archon MCP itself.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from datetime import date
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent.parent
PROMPTS_DIR = SKILL_DIR / "prompts"


def slugify(text: str, max_len: int = 30) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    s = re.sub(r"-+", "-", s)
    return s[:max_len].rstrip("-") or "task"


PROMPT_BODY_MARKER = "<!-- PROMPT-BODY -->"


def render(template: str, subs: dict[str, str]) -> str:
    # Strip template-maintenance preamble (everything before the body marker).
    # Templates are split into a "for maintainers" header and the actual prompt
    # body; only the body is rendered into the final prompt file.
    if PROMPT_BODY_MARKER in template:
        template = template.split(PROMPT_BODY_MARKER, 1)[1].lstrip()
    out = template
    for k, v in subs.items():
        out = out.replace("{{" + k + "}}", v)
    return out


def join_files(files: list[str]) -> str:
    return " ".join(files) if files else "<no files listed>"


def build_subs(task: dict, attempt: int, remediation: str) -> dict[str, str]:
    slug = slugify(task.get("title", "task"))
    files = task.get("files") or task.get("files_in_scope") or []
    if isinstance(files, str):
        files = [f.strip() for f in files.splitlines() if f.strip()]

    return {
        "project_id": task.get("project_id", "<unknown>"),
        "task_id": task.get("id") or task.get("task_id", "<unknown>"),
        "task_title": task.get("title", "<untitled>"),
        "task_description": task.get("description", ""),
        "slug": slug,
        "files_in_scope": "\n".join(f"- `{f}`" for f in files) if files else "<no files listed>",
        "file_paths_joined": join_files(files),
        "acceptance_criteria_verbatim": task.get("acceptance_criteria", "<none provided>"),
        "local_plan_path": task.get("local_plan_path", "<not provided>"),
        "master_plan_path": task.get("master_plan_path", "<not provided>"),
        "date": date.today().isoformat(),
        "remediation_context": remediation if attempt > 1 else "(none — this is attempt 1)",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task-json", required=True, type=Path,
                    help="Path to JSON file containing the Archon task record")
    ap.add_argument("--attempt", type=int, default=1,
                    help="Attempt number (>1 triggers remediation context)")
    ap.add_argument("--remediation-file", type=Path, default=None,
                    help="Path to remediation markdown (required if attempt>1)")
    ap.add_argument("--tmpdir", type=Path, default=Path(tempfile.gettempdir()),
                    help="Where to write prompt files (default: system tmpdir)")
    args = ap.parse_args()

    if not args.task_json.exists():
        print(f"ERROR: task JSON not found: {args.task_json}", file=sys.stderr)
        return 2

    task = json.loads(args.task_json.read_text())

    remediation = ""
    if args.attempt > 1:
        if not args.remediation_file or not args.remediation_file.exists():
            print(f"ERROR: --remediation-file required for attempt>{1}", file=sys.stderr)
            return 2
        remediation = args.remediation_file.read_text()

    subs = build_subs(task, args.attempt, remediation)
    slug = subs["slug"]

    impl_tpl = (PROMPTS_DIR / "impl_seat.template.md").read_text()
    review_tpl = (PROMPTS_DIR / "review_seat.template.md").read_text()

    args.tmpdir.mkdir(parents=True, exist_ok=True)
    impl_path = args.tmpdir / f"codex-impl-{slug}-prompt.txt"
    review_path = args.tmpdir / f"codex-review-{slug}-prompt.txt"

    impl_path.write_text(render(impl_tpl, subs))
    # Review prompt is stable across retries — only write if it doesn't exist.
    if not review_path.exists() or args.attempt == 1:
        review_path.write_text(render(review_tpl, subs))

    print(json.dumps({
        "slug": slug,
        "attempt": args.attempt,
        "impl_prompt": str(impl_path),
        "review_prompt": str(review_path),
        "review_prompt_unchanged": review_path.exists() and args.attempt > 1,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
