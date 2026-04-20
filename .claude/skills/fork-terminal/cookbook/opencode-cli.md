# Purpose

Create a new OpenCode CLI agent to execute the command.

## Variables

DEFAULT_MODEL: groq/kimi-k2-instruct-0905
HEAVY_MODEL: groq/gpt-oss-120b
BASE_MODEL: groq/qwen3-32b
FAST_MODEL: groq/llama-3.3-70b-versatile
LARGE_CONTEXT_MODEL: google/antigravity-gemini-3-flash

## Cost Rules

- **BLOCKED**: `opencode/claude-*` models — these hit the Anthropic API and cost money
- **FREE**: `groq/*` models — Groq LPU inference, rate-limited but no cost
- **FREE**: `google/antigravity-*` models — Antigravity proxy, rate-limited
- Always start with Groq models; fall back to Antigravity only for >200K context tasks

## Instructions

- Before executing the command, run `opencode --help` to understand the command and its options.
- For interactive mode: use `opencode` with no subcommand
- For non-interactive/programmatic mode: use `opencode run` (preferred for forked terminals)
- For the -m (model) argument, use the DEFAULT_MODEL if not specified. If 'fast' is requested, use the FAST_MODEL. If 'heavy' is requested, use the HEAVY_MODEL.
- OpenCode auto-approves tool use — no dangerous/yolo flag needed.
- **Do NOT pass `--dangerously-skip-permissions`** — this flag does not exist in OpenCode (v1.1.x). It exists in Claude Code, not OpenCode. Passing it causes `opencode run` to print help and exit with code 1. Past copy-paste from the Codex executor introduced this bug; see `docs/opencode/SETUP.md` for the forensic note.

## oh-my-opencode Agents

OpenCode uses the oh-my-opencode plugin which provides specialized agents. The default agent (sisyphus) orchestrates sub-agents automatically, but you can select a specific agent with `--agent`:

| Agent | Use For | Invocation |
|-------|---------|-----------|
| (default/sisyphus) | General tasks — it delegates to sub-agents internally | `opencode run "prompt"` |
| explore | Targeted codebase search, "find X", "where is Y" | `opencode run "prompt" --agent explore` |
| librarian | External library docs, GitHub research, Context7 | `opencode run "prompt" --agent librarian` |
| oracle | Deep research, multi-source investigation | `opencode run "prompt" --agent oracle` |
| hephaestus | Code implementation (prefer Codex for this) | `opencode run "prompt" --agent hephaestus` |

## Known Issues

- Groq models do NOT support the `thinking` config that oh-my-opencode adds for non-GPT models. This can cause tool-calling errors where the model gathers data but fails to write output files.
- Antigravity models stall on parallel sub-agent workloads (concurrent request limits). Use for single-agent tasks only.
- The `librarian` agent is classified as a "subagent" by oh-my-opencode, so it falls back to sisyphus when used directly in some configurations.
- Some Groq models have partial tool-calling support — they can READ files via sub-agents but may fail to WRITE output. Always verify output files were actually written.

## Verify Model IDs Before Editing Cascades

Before editing `.claude/workflow_cascades.json` or any oh-my-opencode config, confirm every model ID is in the live registry. Model IDs drift between OpenCode releases, between providers (OpenAI vs OpenCode flat-rate), and between auth states (Groq/Antigravity only appear if authenticated).

```bash
# Dump the live registry
opencode models 2>/dev/null | sort > /tmp/opencode-models.txt

# Dump every model ID referenced by cascades
jq -r '.workflows[].fallback_chain[].model' .claude/workflow_cascades.json | sort -u > /tmp/cascade-models.txt

# Any line output = a model ID that's referenced but does not exist
grep -Fxvf /tmp/opencode-models.txt /tmp/cascade-models.txt
```

Common gotchas observed:
- `openai/gpt-5.3-codex` — does NOT exist; correct is `opencode/gpt-5.3-codex` (flat-rate tier)
- `openai/gpt-5.2` — does NOT exist; correct is `opencode/gpt-5.2`
- `google/antigravity-gemini-3-pro` — does NOT exist; correct is `-pro-high` or `-pro-low`
- `opencode/glm-4.7-free` — does NOT exist; closest is `huggingface/zai-org/GLM-4.7-Flash`
- `groq/*` — only appears if Groq is authenticated (`GROQ_API_KEY` or OAuth). If `opencode models | grep ^groq/` is empty, all `groq/*` entries in cascades silently fall through.

For the automated check, see `.claude/skills/fork-terminal/tools/validate_cascades.py` (Task 9).
