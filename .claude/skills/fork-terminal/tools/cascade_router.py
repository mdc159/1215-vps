#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Workflow cascade router — classifies tasks and returns model fallback chains.

Reads workflow_cascades.json and matches task descriptions to workflow types
by keyword scoring. Returns the primary agent, model, and full fallback chain.

Usage as module:
    from cascade_router import get_cascade, classify_workflow

    cascade = get_cascade("implement user authentication")
    # => {"workflow": "coding", "primary_agent": "hephaestus",
    #     "primary_model": "openai/gpt-5.3-codex",
    #     "fallback_chain": [...], "timeout": 600, ...}

    workflow = classify_workflow("research caching strategies")
    # => "research"

Usage as CLI:
    uv run cascade_router.py "implement user auth"
    uv run cascade_router.py --workflow coding
    uv run cascade_router.py --list

## STABLE CONTRACT — do not break without updating all callers
##
## Callers:
##   - .claude/skills/fork-terminal/tools/opencode_task_executor.py (--workflow flag)
##   - .claude/agents/opencode-delegator.md (classification reference)
##   - .claude/agents/codex-delegator.md (classification reference)
##
## Public API (stable):
##   get_cascade(task_description, workflow=None) -> dict
##   classify_workflow(task_description) -> str
##   get_fallback_models(workflow) -> list[str]
##   get_blocked_models() -> set[str]
##   list_workflows() -> list[str]
##
## Return schema for get_cascade() (stable — callers parse these keys):
##   {
##     "workflow": str,
##     "primary_agent": str | None,
##     "primary_model": str,
##     "fallback_chain": list[{"model": str, "agent": str|None, "tier": str}],
##     "fallback_models": list[str],   # just the model strings, for CLI --fallback-models
##     "timeout": int,
##     "blocked_models": list[str],
##     "web_augmentation": list[dict] | None,
##     "retry_config": dict
##   }
##
## If you modify any of the above, you MUST update all listed callers.
"""

import json
import re
import sys
from pathlib import Path


def _find_config() -> Path:
    """Locate workflow_cascades.json relative to this script or repo root."""
    # Try relative to this script: tools/ -> fork-terminal/ -> skills/ -> .claude/
    script_dir = Path(__file__).resolve().parent
    candidates = [
        script_dir.parent.parent.parent / "workflow_cascades.json",  # .claude/workflow_cascades.json
        script_dir / "workflow_cascades.json",  # same dir fallback
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(
        "workflow_cascades.json not found. Expected at .claude/workflow_cascades.json"
    )


def _load_config(config_path: Path | None = None) -> dict:
    """Load and cache the workflow cascades config."""
    path = config_path or _find_config()
    return json.loads(path.read_text(encoding="utf-8"))


def classify_workflow(task_description: str, config: dict | None = None) -> str:
    """Classify a task description into a workflow type by keyword scoring.

    Returns the workflow name with the highest keyword match score.
    Falls back to the config's default_workflow if no keywords match.
    """
    if config is None:
        config = _load_config()

    text = task_description.lower()
    best_workflow = config.get("default_workflow", "coding")
    best_score = 0

    for workflow_name, workflow_def in config.get("workflows", {}).items():
        score = 0
        for keyword in workflow_def.get("keywords", []):
            kw = keyword.lower()
            # Multi-word keywords get a bonus for specificity
            if kw in text:
                score += len(kw.split())
        if score > best_score:
            best_score = score
            best_workflow = workflow_name

    return best_workflow


def _load_invalid_models(chain: list) -> set[str]:
    """Return the subset of models in `chain` that are NOT in the live OpenCode registry.

    Reads the cached registry at ~/.cache/agent-os/opencode-models.json (populated by
    validate_cascades.py). Returns an empty set if the cache is missing or stale — in
    that case, no pre-flight filtering happens and the caller proceeds with the raw chain.
    """
    import json as _json
    import os as _os
    import time as _time
    cache = Path(_os.path.expanduser("~/.cache/agent-os/opencode-models.json"))
    if not cache.exists():
        return set()
    try:
        data = _json.loads(cache.read_text())
    except (OSError, _json.JSONDecodeError):
        return set()
    # Respect the same 24h TTL as validate_cascades.py
    age = _time.time() - data.get("fetched_at", 0)
    if age > 24 * 3600:
        return set()
    registry = set(data.get("models", []))
    if not registry:
        return set()
    chain_models = {entry["model"] for entry in chain}
    return chain_models - registry


def get_cascade(task_description: str = "",
                workflow: str | None = None,
                config_path: Path | None = None) -> dict:
    """Get the full cascade configuration for a task.

    Args:
        task_description: Natural language task description (used for classification
                         if workflow is not specified)
        workflow: Explicit workflow name (skips classification)
        config_path: Optional path to workflow_cascades.json

    Returns:
        Dict with workflow, primary_agent, primary_model, fallback_chain,
        fallback_models, timeout, blocked_models, web_augmentation, retry_config.
    """
    config = _load_config(config_path)

    # Determine workflow
    if workflow:
        wf_name = workflow
    elif task_description:
        wf_name = classify_workflow(task_description, config)
    else:
        wf_name = config.get("default_workflow", "coding")

    workflows = config.get("workflows", {})
    if wf_name not in workflows:
        raise ValueError(
            f"Unknown workflow '{wf_name}'. Available: {list(workflows.keys())}"
        )

    wf = workflows[wf_name]
    chain = wf.get("fallback_chain", [])
    blocked = set(config.get("blocked_models", []))

    # Filter out blocked models from the chain
    active_chain = [entry for entry in chain if entry["model"] not in blocked]

    # Pre-flight: drop any entry whose model is not in the live OpenCode registry.
    # This prevents silent fall-through when cascades reference stale model IDs
    # (e.g., the 2026-04-19 `openai/gpt-5.3-codex` → `opencode/gpt-5.3-codex` drift).
    # Failures to load the registry are non-fatal — skip filtering and log to stderr.
    invalid_registry = _load_invalid_models(active_chain)
    if invalid_registry:
        active_chain = [
            entry for entry in active_chain if entry["model"] not in invalid_registry
        ]
        import sys as _sys
        print(
            f"[cascade_router] pre-flight dropped {len(invalid_registry)} invalid cascade "
            f"entries: {sorted(invalid_registry)}",
            file=_sys.stderr,
        )

    # Extract primary from first entry in chain
    primary = active_chain[0] if active_chain else {"model": "opencode/gpt-5.3-codex", "agent": None}

    # Fallback models = all models after the primary, as flat list
    fallback_models = [entry["model"] for entry in active_chain[1:]]

    return {
        "workflow": wf_name,
        "primary_agent": wf.get("primary_agent"),
        "primary_model": primary["model"],
        "fallback_chain": active_chain,
        "fallback_models": fallback_models,
        "timeout": wf.get("timeout", 600),
        "blocked_models": list(blocked),
        "web_augmentation": wf.get("web_augmentation"),
        "retry_config": config.get("retry_config", {}),
    }


def get_fallback_models(workflow: str, config_path: Path | None = None) -> list[str]:
    """Get just the fallback model list for a workflow (convenience function)."""
    cascade = get_cascade(workflow=workflow, config_path=config_path)
    return cascade["fallback_models"]


def get_blocked_models(config_path: Path | None = None) -> set[str]:
    """Get the set of blocked (Anthropic API-billed) models."""
    config = _load_config(config_path)
    return set(config.get("blocked_models", []))


def list_workflows(config_path: Path | None = None) -> list[str]:
    """List all available workflow names."""
    config = _load_config(config_path)
    return list(config.get("workflows", {}).keys())


def main():
    """CLI interface for cascade router."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Classify tasks and return model cascade chains"
    )
    parser.add_argument(
        "task_description",
        nargs="?",
        default="",
        help="Task description to classify",
    )
    parser.add_argument(
        "--workflow", "-w",
        default=None,
        help="Explicit workflow name (skip classification)",
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List all available workflows",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to workflow_cascades.json",
    )
    args = parser.parse_args()

    config_path = Path(args.config) if args.config else None

    if args.list:
        config = _load_config(config_path)
        for name, wf in config.get("workflows", {}).items():
            chain_summary = " → ".join(e["model"] for e in wf.get("fallback_chain", []))
            agent = wf.get("primary_agent", "—")
            print(f"  {name:15s} agent={agent:15s} chain: {chain_summary}")
        return

    if not args.task_description and not args.workflow:
        parser.print_help()
        return

    try:
        cascade = get_cascade(
            task_description=args.task_description,
            workflow=args.workflow,
            config_path=config_path,
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(cascade, indent=2))
    else:
        print(f"Workflow:       {cascade['workflow']}")
        print(f"Primary Agent:  {cascade['primary_agent'] or '—'}")
        print(f"Primary Model:  {cascade['primary_model']}")
        print(f"Fallbacks:      {', '.join(cascade['fallback_models']) or '—'}")
        print(f"Timeout:        {cascade['timeout']}s")
        if cascade.get("web_augmentation"):
            tools = ", ".join(t["tool"] for t in cascade["web_augmentation"])
            print(f"Web Tools:      {tools}")


if __name__ == "__main__":
    main()
