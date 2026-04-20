#!/usr/bin/env -S uv run
"""Fork a new terminal window with a command.

Supports --log, --tool, and --delay flags for agent orchestration.

Usage:
    python3 fork_terminal.py "echo hello"
    python3 fork_terminal.py --log --tool codex-task "uv run executor.py ..."
    python3 fork_terminal.py --log --tool opencode-task --delay 30 "uv run executor.py ..."
"""

import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone


def fork_terminal(command: str, tool_label: str | None = None,
                  log: bool = False, delay: int = 0,
                  keep_open: bool = False) -> str:
    """Open a new Terminal window and run the specified command.

    Args:
        command: Shell command to run in the new terminal.
        tool_label: Optional label for log entries (e.g., 'codex-task').
        log: If True, write launch info to <tempdir>/fork-terminal.log.
        delay: Seconds to sleep before launching (for staggered forks).
        keep_open: If True, keep terminal open after command exits (for debugging).
                   Default False — terminal closes when command finishes.
    """
    system = platform.system()
    cwd = os.getcwd()

    # Log the launch
    if log:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool": tool_label or "unknown",
            "command": command[:200],
            "cwd": cwd,
            "delay": delay,
        }
        log_path = os.path.join(tempfile.gettempdir(), "fork-terminal.log")
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    # Stagger delay for quota management
    if delay > 0:
        print(f"[fork-terminal] Delaying {delay}s before launch...")
        time.sleep(delay)

    if system == "Darwin":  # macOS
        shell_command = f"cd {shlex.quote(cwd)} && {command}"
        escaped_shell_command = shell_command.replace("\\", "\\\\").replace('"', '\\"')

        try:
            result = subprocess.run(
                ["osascript", "-e", f'tell application "Terminal" to do script "{escaped_shell_command}"'],
                capture_output=True,
                text=True,
            )
            output = f"stdout: {result.stdout.strip()}\nstderr: {result.stderr.strip()}\nreturn_code: {result.returncode}"
            return output
        except Exception as e:
            return f"Error: {str(e)}"

    elif system == "Windows":
        full_command = f'cd /d "{cwd}" && {command}'
        subprocess.Popen(["cmd", "/c", "start", "cmd", "/k", full_command], shell=True)
        return "Windows terminal launched"

    else:  # Linux / WSL2
        safe_cwd = shlex.quote(cwd)
        suffix = "; exec bash" if keep_open else ""
        terminals = [
            ("gnome-terminal", ["gnome-terminal", "--", "bash", "-c", f"cd {safe_cwd} && {command}{suffix}"]),
            ("konsole", ["konsole", "-e", "bash", "-c", f"cd {safe_cwd} && {command}{suffix}"]),
            ("xfce4-terminal", ["xfce4-terminal", "-e", f"bash -c \"cd {safe_cwd} && {command}{suffix}\""]),
            ("alacritty", ["alacritty", "-e", "bash", "-c", f"cd {safe_cwd} && {command}{suffix}"]),
            ("kitty", ["kitty", "bash", "-c", f"cd {safe_cwd} && {command}{suffix}"]),
            ("xterm", ["xterm", "-e", "bash", "-c", f"cd {safe_cwd} && {command}{suffix}"]),
        ]

        for terminal_name, cmd_array in terminals:
            if shutil.which(terminal_name):
                subprocess.Popen(cmd_array)
                return f"Linux terminal launched ({terminal_name})"

        raise NotImplementedError(
            "No supported terminal emulator found. Install one of: gnome-terminal, konsole, xfce4-terminal, alacritty, kitty, xterm"
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fork a terminal window with a command")
    parser.add_argument("command", help="Command to run in the new terminal")
    parser.add_argument("--log", action="store_true", help="Log launch to /tmp/fork-terminal.log")
    parser.add_argument("--tool", default=None, help="Tool label for log entries")
    parser.add_argument("--delay", type=int, default=0, help="Seconds to delay before launching")
    parser.add_argument("--keep-open", action="store_true", help="Keep terminal open after command exits (for debugging)")
    args = parser.parse_args()

    output = fork_terminal(args.command, tool_label=args.tool, log=args.log,
                           delay=args.delay, keep_open=args.keep_open)
    print(output)
