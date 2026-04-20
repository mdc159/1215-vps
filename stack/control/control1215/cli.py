from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .topology import list_architecture_docs, load_services, load_targets, resolve_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="start-1215")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="Check local prerequisites and repo layout.")
    subparsers.add_parser("targets", help="List supported architecture targets.")
    subparsers.add_parser("docs", help="List architecture review documents.")

    services = subparsers.add_parser("services", help="List services for a target.")
    services.add_argument(
        "--target",
        default="prototype-local",
        help="Target name from stack/topology/targets.json",
    )

    show = subparsers.add_parser("show-target", help="Show details for one target.")
    show.add_argument("target", help="Target name from stack/topology/targets.json")

    return parser


def cmd_doctor() -> int:
    paths = resolve_paths()

    checks = {
        "git": shutil.which("git") is not None,
        "uv": shutil.which("uv") is not None,
        "docker": shutil.which("docker") is not None,
        "repo_root": paths.repo_root.exists(),
        "modules_dir": paths.modules_root.exists(),
        "local_ai_packaged": (paths.modules_root / "local-ai-packaged").exists(),
        "paperclip": (paths.modules_root / "paperclip").exists(),
        "honcho": (paths.modules_root / "honcho").exists(),
        "architecture_docs": paths.docs_root.exists(),
        "topology_manifests": paths.topology_root.exists(),
    }

    for name, ok in checks.items():
        print(f"{name}: {'ok' if ok else 'missing'}")

    return 0 if all(checks.values()) else 1


def cmd_targets() -> int:
    targets = load_targets()["targets"]
    for name, data in targets.items():
        print(f"{name}: {data['summary']}")
    return 0


def cmd_docs() -> int:
    for path in list_architecture_docs():
        print(path.relative_to(resolve_paths().repo_root))
    return 0


def cmd_services(target_name: str) -> int:
    targets = load_targets()["targets"]
    if target_name not in targets:
        print(f"error: unknown target '{target_name}'", file=sys.stderr)
        return 2

    target = targets[target_name]
    services = load_services()["services"]
    selected = set(target["services"])
    for service in services:
        if service["name"] in selected:
            print(
                f"{service['name']}: layer={service['layer']} "
                f"role={service['role']} exposure={service['exposure']}"
            )
    return 0


def cmd_show_target(target_name: str) -> int:
    targets = load_targets()["targets"]
    if target_name not in targets:
        print(f"error: unknown target '{target_name}'", file=sys.stderr)
        return 2
    print(json.dumps(targets[target_name], indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        return cmd_doctor()
    if args.command == "targets":
        return cmd_targets()
    if args.command == "docs":
        return cmd_docs()
    if args.command == "services":
        return cmd_services(args.target)
    if args.command == "show-target":
        return cmd_show_target(args.target)

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

