# Fork Terminal

Fork terminal sessions to new windows with various CLI agents or raw commands.

---

## Purpose

Enables spawning new terminal windows with Claude Code, Codex CLI, OpenCode CLI, or raw CLI commands, optionally including conversation context summaries.

## Activates On

- Fork terminal
- New terminal window
- Spawn CLI agent
- Claude Code in new terminal
- Codex CLI
- OpenCode CLI

## File Count

7 files across 4 directories

## Core Capabilities

### Agent Forking
Launch Claude Code, Codex CLI, or OpenCode CLI in a new terminal with optional context.

### Raw Command Execution
Fork a terminal with any CLI command (ffmpeg, curl, python, etc.).

### Context Summarization
Optionally pass conversation summary to the new agent for continuity.

## Supported Agents

| Agent | Flag | Description |
|-------|------|-------------|
| Claude Code | ENABLE_CLAUDE_CODE | Anthropic's CLI |
| Codex CLI | ENABLE_CODEX_CLI | OpenAI's Codex |
| OpenCode CLI | ENABLE_OPENCODE_CLI | OpenCode agent |
| Raw Commands | ENABLE_RAW_CLI_COMMANDS | Any CLI tool |

## Platform Support

- **macOS**: Uses AppleScript with Terminal.app
- **Windows**: Uses cmd.exe with start command
- **Linux**: Supports gnome-terminal, konsole, xfce4-terminal, alacritty, kitty, xterm

## Directory Structure

```
fork-terminal/
├── SKILL.md           # Main skill instructions
├── README.md          # This file
├── cookbook/          # Agent-specific instructions
│   ├── claude-code.md
│   ├── codex-cli.md
│   ├── opencode-cli.md
│   └── cli-command.md
├── prompts/           # Prompt templates
│   └── fork_summary_user_prompt.md
└── tools/             # Implementation
    └── fork_terminal.py
```

## Related Components

- **Agents**: context-manager
- **Workflows**: feature-development

## Execution Flow

There are two distinct paths through this skill: **interactive** (user asks to fork a terminal) and **programmatic** (another skill/agent delegates work). The diagram below covers every decision point and outcome.

### Entry Points

```mermaid
flowchart TB
    subgraph Entry["Entry Points"]
        U["User: 'fork terminal use codex to X'"]
        S["Skill/Agent: opencode-delegator, codex-delegator,<br/>align-triple, sync-reference, etc."]
    end

    U --> SKILL["SKILL.md reads request"]
    S --> DIRECT["Direct call to fork_terminal.py<br/>or executor script"]
```

### Path 1: Interactive (via SKILL.md)

```mermaid
flowchart TB
    SKILL["SKILL.md: parse user request"] --> HAS_SUMMARY{"User wants<br/>conversation summary?"}

    HAS_SUMMARY -->|Yes| FILL_TEMPLATE["Read fork_summary_user_prompt.md<br/>Fill in conversation history + next request<br/>(in memory, not on disk)"]
    HAS_SUMMARY -->|No| CLASSIFY

    FILL_TEMPLATE --> CLASSIFY{"Which tool type?"}

    CLASSIFY -->|"Raw CLI<br/>(ffmpeg, curl, etc.)"| COOK_CLI["Read cookbook/cli-command.md<br/>Run: command --help"]
    CLASSIFY -->|"Claude Code"| COOK_CC["Read cookbook/claude-code.md<br/>Select model: opus/sonnet/haiku<br/>Add --dangerously-skip-permissions"]
    CLASSIFY -->|"Codex CLI"| COOK_CODEX["Read cookbook/codex-cli.md<br/>Select model: gpt-5.1-codex-max/mini<br/>Add --dangerously-bypass-approvals-and-sandbox"]
    CLASSIFY -->|"OpenCode CLI"| COOK_OC["Read cookbook/opencode-cli.md<br/>Select model: claude-sonnet-4-5/opus-4-6/gpt-5-nano<br/>Interactive mode (no 'run' subcommand)"]

    COOK_CLI --> FORK
    COOK_CC --> FORK
    COOK_CODEX --> FORK
    COOK_OC --> FORK

    FORK["fork_terminal.py<br/>command, --log, --tool, --delay"]
```

### Path 2: Programmatic (via executor scripts)

```mermaid
flowchart TB
    CALLER["Calling skill/agent<br/>(sync-reference, align-triple, etc.)"] --> WRITE_PROMPT["Write prompt to /tmp/*.md"]

    WRITE_PROMPT --> WHICH_EXEC{"Which executor?"}

    WHICH_EXEC -->|OpenCode tasks| OC_EXEC["opencode_task_executor.py<br/>-n slug -m provider/model<br/>--workflow name (optional)<br/>--timeout N --fallback-models X,Y"]
    WHICH_EXEC -->|Codex tasks| CX_EXEC["codex_task_executor.py<br/>-n slug -m model"]
    WHICH_EXEC -->|Codex PRPs| PRP_EXEC["codex_prp_executor.py<br/>PRP file -m model"]

    OC_EXEC --> FORK_OC["fork_terminal.py --log --tool label<br/>'uv run opencode_task_executor.py ...'"]
    CX_EXEC --> FORK_CX["fork_terminal.py --log --tool label<br/>'uv run codex_task_executor.py ...'"]
    PRP_EXEC --> FORK_PRP["fork_terminal.py --log --tool label<br/>'uv run codex_prp_executor.py ...'"]
```

### fork_terminal.py: Platform Detection

```mermaid
flowchart TB
    FORK["fork_terminal.py called"] --> LOG{"--log flag?"}
    LOG -->|Yes| WRITE_LOG["Append to /tmp/fork-terminal.log<br/>{timestamp, tool, command, cwd, delay}"]
    LOG -->|No| DELAY_CHECK

    WRITE_LOG --> DELAY_CHECK{"--delay > 0?"}
    DELAY_CHECK -->|Yes| SLEEP["sleep(delay) seconds<br/>(quota staggering)"]
    DELAY_CHECK -->|No| PLATFORM

    SLEEP --> PLATFORM{"platform.system()"}

    PLATFORM -->|Darwin| MAC["osascript: Terminal.app do script"]
    PLATFORM -->|Windows| WIN["cmd /c start cmd /k"]
    PLATFORM -->|Linux/WSL| LINUX_DETECT{"Detect terminal emulator"}

    LINUX_DETECT -->|gnome-terminal| GNOME["gnome-terminal -- bash -c '...'"]
    LINUX_DETECT -->|konsole| KDE["konsole -e bash -c '...'"]
    LINUX_DETECT -->|xfce4-terminal| XFCE["xfce4-terminal -e '...'"]
    LINUX_DETECT -->|alacritty| ALAC["alacritty -e bash -c '...'"]
    LINUX_DETECT -->|kitty| KITTY["kitty bash -c '...'"]
    LINUX_DETECT -->|xterm| XTERM["xterm -e bash -c '...'"]
    LINUX_DETECT -->|None found| ERROR["NotImplementedError"]

    MAC --> XTERM_OPEN["New terminal window opens<br/>running command in cwd"]
    WIN --> XTERM_OPEN
    GNOME --> XTERM_OPEN
    KDE --> XTERM_OPEN
    XFCE --> XTERM_OPEN
    ALAC --> XTERM_OPEN
    KITTY --> XTERM_OPEN
    XTERM --> XTERM_OPEN
```

### OpenCode Executor: Full Lifecycle

```mermaid
flowchart TB
    START["opencode_task_executor.py<br/>prompt_file, -n name, -m model"] --> WORKFLOW{"--workflow flag?"}

    WORKFLOW -->|Yes| CASCADE["cascade_router.py<br/>classify_workflow() or explicit name<br/>Read workflow_cascades.json"]
    WORKFLOW -->|No| BLOCKED_CHECK

    CASCADE --> OVERRIDE["Override: model, agent,<br/>fallback_models, timeout<br/>from cascade config"]
    OVERRIDE --> BLOCKED_CHECK

    BLOCKED_CHECK{"Model in<br/>BLOCKED_MODELS?<br/>(Anthropic API)"}
    BLOCKED_CHECK -->|Yes| BLOCK_EXIT["Write done.json<br/>status: error<br/>error_type: BLOCKED_MODEL<br/>EXIT"]
    BLOCKED_CHECK -->|No| READ_PROMPT

    READ_PROMPT["Read prompt from file<br/>Append output instructions:<br/>'write summary to /tmp/...-summary.md'"]
    READ_PROMPT -->|File not found| PROMPT_ERR["Write done.json<br/>status: error<br/>error_type: PROMPT_READ_FAILED<br/>EXIT"]
    READ_PROMPT -->|Success| MODEL_LOOP

    MODEL_LOOP["For each model in:<br/>[primary] + [fallback_models]"]
    MODEL_LOOP --> ATTEMPT["subprocess.run:<br/>opencode run PROMPT --format default<br/>-m MODEL (or --agent AGENT)<br/>stdout → /tmp/...-output.log<br/>timeout: N seconds"]

    ATTEMPT -->|exit 0| SUCCESS["Write done.json<br/>status: success<br/>duration, model, retries<br/>EXIT"]
    ATTEMPT -->|Timeout| TIMEOUT["Write done.json<br/>status: timeout<br/>error_type: TIMEOUT<br/>EXIT"]
    ATTEMPT -->|Rate limited / 429| RETRY{"More retries<br/>for this model?"}
    ATTEMPT -->|Quota exhausted| NEXT_MODEL{"More fallback<br/>models?"}
    ATTEMPT -->|Other error| FAIL["Write done.json<br/>status: error<br/>error_type: EXEC_FAILED<br/>EXIT"]

    RETRY -->|Yes| WAIT["sleep(retry_delay × attempt)"] --> ATTEMPT
    RETRY -->|No| NEXT_MODEL
    NEXT_MODEL -->|Yes| MODEL_LOOP
    NEXT_MODEL -->|No| EXHAUSTED["Write done.json<br/>status: error<br/>error_type: ALL_RETRIES_EXHAUSTED<br/>EXIT"]
```

### Codex Executor: Full Lifecycle

```mermaid
flowchart TB
    START["codex_task_executor.py<br/>prompt_file, -n name, -m model"] --> READ["Read prompt from file<br/>Append: 'write summary to /tmp/...-summary.md'"]

    READ -->|File not found| PROMPT_ERR["Write done.json<br/>status: error, PROMPT_READ_FAILED<br/>EXIT"]
    READ -->|Success| EXEC["subprocess.run:<br/>codex exec --dangerously-bypass-approvals-and-sandbox<br/>-c 'model=MODEL' PROMPT<br/>stdout → /tmp/codex-task-NAME-output.log<br/>timeout: 600s"]

    EXEC -->|exit 0| SUCCESS["Write done.json<br/>status: success<br/>EXIT"]
    EXEC -->|Timeout| TIMEOUT["Write done.json<br/>status: timeout<br/>EXIT"]
    EXEC -->|CLI not found| NOTFOUND["Write done.json<br/>status: error, CLI_NOT_FOUND<br/>EXIT"]
    EXEC -->|Other error| FAIL["Write done.json<br/>status: error<br/>EXIT"]
```

### Caller Polling: How the Main Session Knows It's Done

```mermaid
flowchart TB
    LAUNCH["Main session launches fork<br/>via fork_terminal.py"] --> POLL["Poll every 15s:<br/>Does /tmp/*-done.json exist?"]

    POLL -->|Not yet| POLL
    POLL -->|Found| READ_DONE["Read done.json"]

    READ_DONE --> CHECK{"status field?"}

    CHECK -->|success| READ_OUTPUT["Read output files:<br/>1. Target file (e.g. docs/exploration/...md)<br/>2. /tmp/*-summary.md<br/>3. /tmp/*-output.log"]
    CHECK -->|error| CLASSIFY_ERR{"error_type?"}
    CHECK -->|timeout| RETRY_OR_FAIL["Retry with fallback model<br/>or report timeout to user"]

    CLASSIFY_ERR -->|RATE_LIMITED| RETRY_FALLBACK["Relaunch with fallback model"]
    CLASSIFY_ERR -->|BLOCKED_MODEL| SWITCH["Switch to non-Anthropic model"]
    CLASSIFY_ERR -->|CLI_NOT_FOUND| INSTALL["Tell user to install CLI"]
    CLASSIFY_ERR -->|EXEC_FAILED| READ_LOG["Read output.log for diagnostics"]

    READ_OUTPUT --> VERIFY{"Did the model<br/>write the target file?"}
    VERIFY -->|Yes, with new content| USE_DATA["Use fork-sourced data<br/>in synthesis/report"]
    VERIFY -->|No, file unchanged| EXTRACT_LOG["Extract gathered data<br/>from output.log<br/>(model read files but<br/>couldn't write output)"]
    VERIFY -->|File missing| EXTRACT_LOG

    EXTRACT_LOG --> MANUAL["Parse log for structured data<br/>or re-run with different model"]
```

### Output File Map

```
/tmp/
├── fork-terminal.log                          # All fork launches (append-only)
├── opencode-task-{name}-output.log            # Full OpenCode stdout+stderr
├── opencode-task-{name}-done.json             # Completion flag (poll this)
├── opencode-task-{name}-summary.md            # Summary (if model writes it)
├── codex-task-{name}-output.log               # Full Codex stdout+stderr
├── codex-task-{name}-done.json                # Completion flag (poll this)
├── codex-task-{name}-summary.md               # Summary (if model writes it)
└── codex-prp-{name}-done.json                 # PRP completion flag

Target files (written by the model, not the executor):
├── docs/exploration/sync-reference-*.md       # sync-reference outputs
├── docs/audits/align-triple-*/                # align-triple outputs
└── (whatever the prompt instructs)
```

---

**Part of**: claude-code-templates
