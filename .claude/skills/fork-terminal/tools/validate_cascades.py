#!/usr/bin/env python3
"""Validate every model ID in .claude/workflow_cascades.json against the live OpenCode registry.

Also validates `.claude/workflow_cascades.json` against a cached registry if
`opencode` is not available (useful in CI or on machines without OpenCode installed).

Exit codes:
    0 — all cascade entries are valid
    1 — one or more cascade entries reference models not in the registry
    2 — could not determine registry (no cache, no CLI)
    3 — config file missing or malformed

Usage:
    python3 validate_cascades.py                         # check all cascades
    python3 validate_cascades.py --workflow exploration  # check one cascade
    python3 validate_cascades.py --json                  # JSON output for hooks
    python3 validate_cascades.py --refresh-cache         # force refresh of model cache
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
CASCADE_CONFIG = REPO_ROOT / ".claude" / "workflow_cascades.json"
CACHE_PATH = Path(os.path.expanduser("~/.cache/agent-os/opencode-models.json"))
CACHE_TTL_SECONDS = 24 * 3600  # 24 hours


def load_cached_registry() -> set[str] | None:
    if not CACHE_PATH.exists():
        return None
    try:
        data = json.loads(CACHE_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    age = time.time() - data.get("fetched_at", 0)
    if age > CACHE_TTL_SECONDS:
        return None
    return set(data.get("models", []))


def fetch_live_registry() -> set[str] | None:
    try:
        result = subprocess.run(
            ["opencode", "models"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    models = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    return models if models else None


def save_registry_cache(models: set[str]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps({
        "fetched_at": time.time(),
        "models": sorted(models),
    }))


def get_registry(refresh: bool = False) -> set[str] | None:
    """Return the set of valid model IDs. Prefers live `opencode models`, falls back to cache."""
    if not refresh:
        cached = load_cached_registry()
        if cached is not None:
            return cached
    live = fetch_live_registry()
    if live is not None:
        save_registry_cache(live)
        return live
    # Live fetch failed — return stale cache if we have it (better than nothing)
    if CACHE_PATH.exists():
        try:
            data = json.loads(CACHE_PATH.read_text())
            return set(data.get("models", []))
        except (OSError, json.JSONDecodeError):
            pass
    return None


def suggest_nearest(bad_id: str, registry: set[str], limit: int = 3) -> list[str]:
    """Return up to `limit` nearest valid model IDs using simple substring scoring."""
    if not registry:
        return []
    # Strip provider prefix for matching
    bad_tail = bad_id.split("/", 1)[-1]
    scored = []
    for candidate in registry:
        cand_tail = candidate.split("/", 1)[-1]
        # Score = length of longest common substring (rough)
        score = _lcs_len(bad_tail, cand_tail)
        if score > 0:
            scored.append((score, candidate))
    scored.sort(reverse=True)
    return [c for _, c in scored[:limit]]


def _lcs_len(a: str, b: str) -> int:
    if not a or not b:
        return 0
    # Simple longest-common-substring length
    best = 0
    for i in range(len(a)):
        for j in range(len(b)):
            k = 0
            while i + k < len(a) and j + k < len(b) and a[i + k] == b[j + k]:
                k += 1
            if k > best:
                best = k
    return best


def validate(config_path: Path, registry: set[str] | None, workflow_filter: str | None = None) -> dict:
    """Return a report dict with invalid entries and suggestions."""
    try:
        config = json.loads(config_path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return {"error": f"Could not read {config_path}: {e}", "exit_code": 3}

    workflows = config.get("workflows", {})
    if workflow_filter:
        workflows = {k: v for k, v in workflows.items() if k == workflow_filter}
        if not workflows:
            return {"error": f"Unknown workflow: {workflow_filter}", "exit_code": 3}

    issues = []
    checked = 0
    for wf_name, wf in workflows.items():
        for idx, entry in enumerate(wf.get("fallback_chain", [])):
            model = entry.get("model")
            if not model:
                continue
            checked += 1
            if registry is not None and model not in registry:
                issues.append({
                    "workflow": wf_name,
                    "position": idx + 1,
                    "model": model,
                    "agent": entry.get("agent"),
                    "tier": entry.get("tier"),
                    "suggestions": suggest_nearest(model, registry),
                })

    return {
        "registry_available": registry is not None,
        "registry_size": len(registry) if registry else 0,
        "workflows_checked": len(workflows),
        "models_checked": checked,
        "issues": issues,
    }


def format_report(report: dict) -> str:
    if "error" in report:
        return f"ERROR: {report['error']}"

    lines = [
        f"Cascade validation report",
        f"  Registry: {'live (' + str(report['registry_size']) + ' models)' if report['registry_available'] else 'UNAVAILABLE'}",
        f"  Workflows checked: {report['workflows_checked']}",
        f"  Model IDs checked: {report['models_checked']}",
        f"  Invalid entries: {len(report['issues'])}",
    ]

    if not report["issues"]:
        lines.append("")
        lines.append("✓ All cascade entries valid.")
        return "\n".join(lines)

    lines.append("")
    lines.append("Invalid cascade entries:")
    for issue in report["issues"]:
        lines.append(
            f"  [{issue['workflow']}] position {issue['position']}: {issue['model']}"
            f" (tier={issue['tier']}, agent={issue['agent']})"
        )
        if issue["suggestions"]:
            lines.append(f"      → suggested: {', '.join(issue['suggestions'])}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", help="Check only one workflow cascade")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--refresh-cache", action="store_true", help="Force live registry fetch")
    parser.add_argument("--config", type=Path, default=CASCADE_CONFIG,
                        help="Path to workflow_cascades.json")
    args = parser.parse_args()

    if not args.config.exists():
        msg = f"Config not found: {args.config}"
        print(msg, file=sys.stderr)
        if args.json:
            print(json.dumps({"error": msg, "exit_code": 3}))
        return 3

    registry = get_registry(refresh=args.refresh_cache)
    report = validate(args.config, registry, workflow_filter=args.workflow)

    if "error" in report:
        if args.json:
            print(json.dumps(report))
        else:
            print(f"ERROR: {report['error']}", file=sys.stderr)
        return report.get("exit_code", 3)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(format_report(report))

    if not report["registry_available"]:
        return 2
    return 1 if report["issues"] else 0


if __name__ == "__main__":
    sys.exit(main())
