---
name: install-memory-compiler
description: |
  Install claude-memory-compiler into the current repo with required patches.

  Usage: /install-memory-compiler

  Clones coleam00/claude-memory-compiler, wires up the Claude Code hooks
  (SessionEnd, PreCompact, SessionStart), and applies two patches:
    1. ANTHROPIC_API_KEY env-clear fix (prevents FLUSH_ERROR from OAuth shadowing)
    2. CLAUDE_MEMORY_KB env var support (opt-in shared KB, e.g. Obsidian vault)

  Run once per repo. Upstream-compatible — preserves default behavior when
  CLAUDE_MEMORY_KB is unset.

user-invocable: true
allowed-tools:
  - Bash(*)
  - Read
  - Write
  - Edit
  - Glob
  - Grep
---

# Install claude-memory-compiler

Execute the install prompt below exactly. It is a single paste from
upstream (`coleam00/claude-memory-compiler` README) extended with two
required patches we've upstreamed as local standard.

---

Clone https://github.com/coleam00/claude-memory-compiler into this project. Set up the Claude Code hooks so my conversations automatically get captured into daily logs, compiled into a knowledge base, and injected back into future sessions. Read the AGENTS.md for the full technical reference on how everything works.

Before enabling the hooks, patch the Agent SDK scripts to work around a known auth bug: Claude Code exports an `ANTHROPIC_API_KEY` for the current session, and any subprocess spawned by a hook inherits it. The bundled `claude` CLI used by the memory compiler then tries to authenticate with that stale session key instead of falling back to your OAuth credentials, and every flush/compile/query fails with exit code 1 (visible as `FLUSH_ERROR` in the daily log).

The fix: in every script under `claude-memory-compiler/scripts/` that constructs a `ClaudeAgentOptions(...)` (typically `flush.py`, `compile.py`, `query.py`, and `lint.py` if present), add `env={"ANTHROPIC_API_KEY": ""}` as a keyword argument to that constructor. An empty string is required — omitting the variable is not enough, it must be explicitly cleared so the child process does not inherit the parent's value. Skip any script that does not construct `ClaudeAgentOptions`. Verify the patch with `grep -l 'env={"ANTHROPIC_API_KEY": ""}' claude-memory-compiler/scripts/*.py` and confirm each relevant script is listed before enabling hooks.

Second patch: make the KB location environment-aware so all my memory compiler instances can share a single KB when one exists, while still defaulting to the upstream standalone behavior. Edit `claude-memory-compiler/scripts/config.py`:

1. Add `import os` at the top with the other imports.
2. Replace the line `KNOWLEDGE_DIR = ROOT_DIR / "knowledge"` with:
   ```python
   _env_kb = os.environ.get("CLAUDE_MEMORY_KB")
   KNOWLEDGE_DIR = Path(_env_kb).expanduser() if _env_kb else ROOT_DIR / "knowledge"
   ```

This preserves Cole's upstream default (local `knowledge/` dir) when the env var is unset — correct behavior for VPS / fresh-clone / CI contexts. On machines where I want a shared KB (e.g., my M6800 where the Obsidian vault lives), I export `CLAUDE_MEMORY_KB=/path/to/shared/kb` in my shell profile and every memory compiler instance picks it up automatically. Do not hardcode any machine-specific path in `config.py` itself.
