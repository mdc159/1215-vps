---
name: codex-delegator-execution-flow
description: |
  Reference documentation for the codex-delegator agent's execution flow.
  Mermaid flowcharts covering task classification, fork execution, monitoring,
  sandbox validation, and reporting. Not an executable agent — a companion
  reference for understanding the codex-delegator lifecycle.
model: inherit
color: gray
---

# Codex Delegator — Execution Flow Reference

Complete decision tree for every path through the codex-delegator agent, from invocation to final report.

## Who Calls This Agent

```mermaid
flowchart TB
    subgraph Callers["Callers"]
        USER["/codex slash command<br/>(command mode)"]
        PARENT["Parent agent via Task tool<br/>subagent_type='codex-delegator'<br/>(sub-agent mode)"]
        SKILL["Skill orchestrator<br/>align-triple, sync-reference, etc.<br/>(structured mode)"]
    end

    USER --> DETECT
    PARENT --> DETECT
    SKILL --> DETECT

    DETECT{"Input starts with<br/>'mode: structured'?"}
    DETECT -->|Yes| STRUCTURED["Structured Mode<br/>(skip Steps 1-4, go to Step 5)"]
    DETECT -->|No| BARE_CHECK{"Empty input?<br/>(/codex with no args)"}
    BARE_CHECK -->|Yes| HELP["Print usage help<br/>EXIT"]
    BARE_CHECK -->|No| STEP1["Step 1: Classify Task"]
```

## Full Path: Standard Mode (Steps 1-9)

### Step 1: Task Classification

```mermaid
flowchart TB
    INPUT["Task description from caller"] --> ARCHON_CHECK{"Contains 'Archon Task ID'<br/>AND validate/review/criteria?"}
    ARCHON_CHECK -->|Yes| TYPE_REVIEW["archon-task-review<br/>model: gpt-5.3-codex"]
    ARCHON_CHECK -->|No| PRP_CHECK{"File path ending .md<br/>with Acceptance Criteria?"}

    PRP_CHECK -->|Yes| TYPE_PRP["prp<br/>model: gpt-5.3-codex"]
    PRP_CHECK -->|No| KEYWORD{"Keyword scan"}

    KEYWORD --> K_CI{"CI, pipeline,<br/>actions failing?"} -->|Yes| TYPE_CI["fix-ci<br/>skill: /gh-fix-ci"]
    KEYWORD --> K_PR{"PR comments,<br/>review, #NNN?"} -->|Yes| TYPE_PR["address-pr<br/>skill: /gh-address-comments"]
    KEYWORD --> K_SEC{"security, audit,<br/>OWASP?"} -->|Yes| TYPE_SEC["security<br/>skill: /security-best-practices"]
    KEYWORD --> K_E2E{"E2E, playwright,<br/>browser test?"} -->|Yes| TYPE_E2E["e2e-test<br/>skill: /playwright"]
    KEYWORD --> K_THREAT{"threat model,<br/>attack surface?"} -->|Yes| TYPE_THREAT["threat-model<br/>skill: /security-threat-model"]
    KEYWORD --> K_DOC{"document, docs,<br/>README?"} -->|Yes| TYPE_DOC["docs<br/>model: gpt-5.1-codex-mini<br/>skill: /doc"]
    KEYWORD --> K_FIX{"fix bug,<br/>regression?"} -->|Yes| TYPE_FIX["bugfix"]
    KEYWORD --> K_REF{"refactor,<br/>restructure?"} -->|Yes| TYPE_REF["refactor"]
    KEYWORD --> K_IMPL{"implement, add,<br/>build, create?"} -->|Yes| TYPE_IMPL["implement"]
    KEYWORD --> K_DEFAULT["Default: implement"]

    subgraph Override["User Model Override"]
        FAST["'fast' or 'mini' → gpt-5.1-codex-mini"]
        HEAVY["'heavy' or 'max' → gpt-5.3-codex"]
    end
```

### Step 2: Prerequisites

```mermaid
flowchart TB
    CHECK["Step 2: Check Prerequisites"] --> CODEX_INSTALLED{"which codex"}
    CODEX_INSTALLED -->|OK| SET_TMPDIR["Set TMPDIR<br/>(cross-platform: python3 tempfile)"]
    CODEX_INSTALLED -->|MISSING| ABORT["Report: Codex CLI missing<br/>npm install -g @openai/codex<br/>EXIT"]
    SET_TMPDIR --> STEP3["Step 3"]
```

### Steps 3-4: Context Gathering & Prompt Construction

```mermaid
flowchart TB
    STEP3["Step 3: Package Context"] --> IS_PRP{"Task type = prp?"}

    IS_PRP -->|Yes| SKIP_CONTEXT["Skip — PRP executor<br/>builds its own prompt"] --> STEP5_PRP

    IS_PRP -->|No| GATHER["Gather context:<br/>1. Master plan (verify Archon Project ID)<br/>2. CLAUDE.md (first 100 lines)<br/>3. Referenced files (up to 3, 200 lines each)<br/>4. PR context via gh (if #NNN)<br/>5. CI status via gh (if fix-ci)<br/>6. git diff --stat HEAD~3"]

    GATHER --> ID_MATCH{"Plan file Archon Project ID<br/>matches caller's ID?"}
    ID_MATCH -->|No| ABORT_ID["ABORT: ID MISMATCH<br/>Wrong plan file<br/>EXIT"]
    ID_MATCH -->|Yes| STEP4

    STEP4["Step 4: Construct Prompt"] --> PROMPT_TYPE{"Task type?"}

    PROMPT_TYPE -->|archon-task-review| REVIEW_PROMPT["Build review prompt:<br/>Identity chain + acceptance criteria<br/>+ review checklist + output template<br/>→ $TMPDIR/codex-task-{slug}-prompt.txt"]
    PROMPT_TYPE -->|all others| GENERIC_PROMPT["Build generic prompt:<br/>Identity chain + task + context<br/>+ conventions + output requirements<br/>→ $TMPDIR/codex-task-{slug}-prompt.txt"]

    REVIEW_PROMPT --> STEP5
    GENERIC_PROMPT --> STEP5

    STEP5["Step 5: Fork Execution"]
    STEP5_PRP["Step 5: Fork PRP Execution"]
```

### Step 5: Fork Execution

```mermaid
flowchart TB
    STEP5{"Task type = prp?"} -->|Yes| FORK_PRP["fork_terminal.py --log --tool codex-prp<br/>'uv run codex_prp_executor.py {prp_path} -m {model}'"]
    STEP5 -->|No| FORK_TASK["fork_terminal.py --log --tool codex-task<br/>'uv run codex_task_executor.py {prompt_file} -n {slug} -m {model}'"]

    FORK_PRP --> XTERM["xterm opens<br/>Executor runs in separate process"]
    FORK_TASK --> XTERM

    subgraph XtermProcess["Inside the xterm (hands off)"]
        EXEC_READ["Executor reads prompt file"]
        EXEC_READ --> EXEC_APPEND["Appends output instructions:<br/>'write summary to /tmp/...-summary.md'"]
        EXEC_APPEND --> EXEC_RUN["subprocess.run:<br/>codex exec --dangerously-bypass...<br/>-c 'model=MODEL' PROMPT"]
        EXEC_RUN -->|exit 0| EXEC_DONE_OK["Write done.json<br/>status: success"]
        EXEC_RUN -->|timeout| EXEC_DONE_TO["Write done.json<br/>status: timeout"]
        EXEC_RUN -->|error| EXEC_DONE_ERR["Write done.json<br/>status: error"]
    end

    XTERM --> STEP6["Step 6: Poll for completion"]
```

### Step 6: Monitoring Loop

```mermaid
flowchart TB
    STEP6["Step 6: Monitor"] --> GRACE["Wait 15s<br/>(Codex startup grace)"]
    GRACE --> POLL["Poll: cat done.json"]

    POLL -->|File exists| PARSE["Parse JSON"]
    POLL -->|Not found| ITER_CHECK{"Iteration count?"}

    ITER_CHECK -->|"< 40 (~10 min)"| PROGRESS{"Every 4th iteration?"}
    ITER_CHECK -->|"= 40"| TIMEOUT_EXIT["Read last 50 lines of output.log<br/>Report timeout to caller<br/>EXIT"]

    PROGRESS -->|Yes| READ_TAIL["Read last 20 lines of output.log<br/>(progress check)"] --> WAIT
    PROGRESS -->|No| WAIT["Wait 15s"] --> POLL

    PARSE --> STEP7["Step 7: Sandbox (optional)"]

    subgraph ModeRules["Reporting During Poll"]
        CMD_MODE["Command mode:<br/>Show progress every 60s"]
        SUB_MODE["Sub-agent mode:<br/>Stay silent during polling"]
    end
```

### Step 7: Optional Sandbox Validation

```mermaid
flowchart TB
    STEP7["Step 7: Sandbox?"] --> SBX_CHECK{"Should sandbox?"}

    SBX_CHECK -->|"User said 'test in sandbox'"| SBX_YES
    SBX_CHECK -->|"Task type = e2e-test"| SBX_YES
    SBX_CHECK -->|"Codex produced test files<br/>AND project has test runner"| SBX_YES
    SBX_CHECK -->|"Task = docs/security/<br/>threat-model/address-pr"| SBX_SKIP["Skip sandbox"]
    SBX_CHECK -->|"No triggers"| SBX_SKIP

    SBX_YES["Create E2B sandbox"] --> SBX_UPLOAD["Upload repo"]
    SBX_UPLOAD --> SBX_DETECT{"Detect deps"}

    SBX_DETECT -->|package.json| NPM["npm install"]
    SBX_DETECT -->|pyproject.toml| UV["uv sync"]
    SBX_DETECT -->|requirements.txt| PIP["pip install -r"]
    SBX_DETECT -->|go.mod| GO["go mod download"]

    NPM --> SBX_TEST["Run tests in sandbox"]
    UV --> SBX_TEST
    PIP --> SBX_TEST
    GO --> SBX_TEST

    SBX_TEST --> SBX_READ["Read test results"]
    SBX_READ --> SBX_KILL["Kill sandbox (~$0.13/hr)"]
    SBX_KILL --> STEP8

    SBX_SKIP --> STEP8["Step 8: Summarize"]
```

### Steps 8-9: Report & Persist

```mermaid
flowchart TB
    STEP8["Step 8: Summarize Results"] --> READ_TYPE{"Task type?"}

    READ_TYPE -->|PRP| READ_PRP["Read /tmp/codex-prp-{name}-report.json<br/>Extract: status, files, tests, criteria"]
    READ_TYPE -->|Other| READ_DONE["Read done.json + summary.md"]

    READ_DONE --> HAS_SUMMARY{"summary.md exists?"}
    HAS_SUMMARY -->|Yes| READ_SUM["Read summary.md"]
    HAS_SUMMARY -->|No| FALLBACK_LOG["Fallback: read last 100 lines<br/>of output.log"]

    READ_PRP --> VERIFY_ID
    READ_SUM --> VERIFY_ID
    FALLBACK_LOG --> VERIFY_ID

    VERIFY_ID["Verify identity chain:<br/>1. Archon Project ID matches<br/>2. Archon Task ID matches<br/>3. Plan Verified = yes"]

    VERIFY_ID -->|All match| BUILD_REPORT["Build Codex Delegation Report"]
    VERIFY_ID -->|Mismatch| ID_FAIL["Mark report: ID_MISMATCH<br/>Do NOT mark as PASS"]

    BUILD_REPORT --> VERDICT{"Verdict?"}
    ID_FAIL --> BUILD_REPORT

    VERDICT -->|PASS| REPORT_PASS["Report with Changes + Summary"]
    VERDICT -->|FAIL/PARTIAL| REPORT_FAIL["Report with Changes + Summary<br/>+ Remediation section:<br/>  - Complexity rating<br/>  - Suggested fixes with code<br/>  - Re-validation command"]

    REPORT_PASS --> STEP9
    REPORT_FAIL --> STEP9

    STEP9["Step 9: Persist to disk<br/>.claude/validation-results/{slug}-{timestamp}.md<br/>Includes: full report + verdict +<br/>Archon IDs + raw output paths"]

    STEP9 --> RETURN{"Invocation mode?"}

    RETURN -->|Sub-agent| RETURN_TERSE["Return structured report<br/>No follow-up suggestions<br/>EXIT"]
    RETURN -->|Command| RETURN_HELP["Return report +<br/>Offer: code-review? sandbox? commit?<br/>EXIT"]
```

## Full Path: Structured Mode

```mermaid
flowchart TB
    INPUT["mode: structured<br/>prompt_file: /tmp/prompt.md<br/>slug: my-task<br/>model: gpt-5.3-codex<br/>tool_label: codex-my-task<br/>delay: 5 (optional)"] --> PARSE["Parse key-value params"]

    PARSE --> PREREQ["Step 2 only:<br/>Check codex CLI installed"]
    PREREQ -->|Missing| ABORT["Report CLI missing, EXIT"]
    PREREQ -->|OK| BUILD_CMD

    BUILD_CMD["Build exact command:<br/>fork_terminal.py --log<br/>--tool {tool_label}<br/>[--delay {delay}]<br/>'uv run codex_task_executor.py<br/>{prompt_file} -n {slug} -m {model}'"]

    BUILD_CMD --> FORK["Step 5: Fork terminal"]
    FORK --> MONITOR["Step 6: Poll done.json<br/>every 15s, max 40 iterations"]

    MONITOR -->|done.json found| VALIDATE["Post-completion validation:<br/>1. Read output.log<br/>2. Search for JSON block<br/>3. Parse JSON<br/>4. Check claims array exists<br/>5. Check claims non-empty<br/>6. Spot-check first claim fields"]

    VALIDATE --> VAL_STATUS{"Validation result?"}

    VAL_STATUS -->|valid| REPORT_OK["Structured Report:<br/>Status: success<br/>Validation: valid<br/>Claims: N"]
    VAL_STATUS -->|invalid_json| REPORT_BAD["Structured Report:<br/>Status: success (process)<br/>Validation: invalid_json"]
    VAL_STATUS -->|empty_claims| REPORT_EMPTY["Structured Report:<br/>Status: success (process)<br/>Validation: empty_claims"]
    VAL_STATUS -->|no_json_found| REPORT_NONE["Structured Report:<br/>Status: success (process)<br/>Validation: no_json_found"]

    REPORT_OK --> RETURN["Return report, STOP"]
    REPORT_BAD --> RETURN
    REPORT_EMPTY --> RETURN
    REPORT_NONE --> RETURN

    MONITOR -->|Timeout| REPORT_TO["Structured Report:<br/>Status: timeout"] --> RETURN
```

## Output File Map

```
$TMPDIR/
├── codex-task-{slug}-prompt.txt          # Constructed prompt (Step 4)
├── codex-task-{slug}-output.log          # Full Codex stdout+stderr
├── codex-task-{slug}-done.json           # Completion flag (poll this)
├── codex-task-{slug}-summary.md          # Codex-written summary
├── codex-prp-{name}-output.log           # PRP variant
├── codex-prp-{name}-done.json            # PRP completion flag
├── codex-prp-{name}-report.json          # PRP structured report
└── fork-terminal.log                     # All fork launches (append)

Project:
└── .claude/validation-results/
    └── {slug}-{timestamp}.md             # Persisted report (Step 9)
```

## Failure Modes

| Failure | Where | done.json Status | Recovery |
|---------|-------|-----------------|----------|
| Codex CLI not installed | Step 2 | N/A (aborts before fork) | `npm install -g @openai/codex` |
| Prompt file unreadable | Executor startup | `error`, `PROMPT_READ_FAILED` | Check path, re-write prompt |
| Codex timeout (>10 min) | Executor runtime | `timeout` | Increase timeout, simplify task |
| Codex exit non-zero | Executor runtime | `error`, `EXEC_FAILED` | Read output.log for diagnostics |
| Rate limited (429) | Executor runtime | `error`, retries exhausted | Wait, try different model |
| Auth failure | Codex runtime | `error` (exit non-zero) | Check GPT+ OAuth or OPENAI_API_KEY |
| Archon ID mismatch | Step 3 or Step 8 | N/A | Wrong plan file, verify Project ID |
| Process-level success but no output | Step 8 | `success` (exit 0) | Read output.log, model gathered data but couldn't write. Model/tool issue. |
| Bash permission denied | Step 5 (sub-agent) | N/A (never forks) | Delegator needs `Bash(*)` in tool permissions |
