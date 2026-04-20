# Example Flows — archon-dual-fork

Worked examples of how an orchestrator drives the skill. Two cadences shown:
sequential (one task at a time) and pipelined (review task N while impl task N+1).

Both assume the orchestrator is Claude Code with Archon MCP access.

## Sequential — one task end-to-end

### 1. Pull and claim the task

```python
# Archon MCP call from the orchestrator
task = find_tasks(task_id="<UUID>")
manage_task("update", task_id=task["id"], status="doing", assignee="codex-impl")
```

Write the task JSON to disk so build_prompts.py can read it:

```bash
# orchestrator writes /tmp/task-<slug>.json containing:
# {
#   "id": "<uuid>",
#   "project_id": "<uuid>",
#   "title": "Add foo handler to bar service",
#   "description": "...",
#   "acceptance_criteria": "1. Handler returns 200 on happy path\n2. ...",
#   "files": ["src/bar/foo.py", "tests/bar/test_foo.py"],
#   "local_plan_path": "docs/plans/bar-service.md",
#   "master_plan_path": "docs/plans/systems-tightening-master-plan.md"
# }
```

### 2. Preflight + build prompts

```bash
uv run .claude/skills/archon-dual-fork/scripts/preflight.py
uv run .claude/skills/archon-dual-fork/scripts/build_prompts.py \
  --task-json /tmp/task-add-foo.json
# emits: /tmp/codex-impl-add-foo-handler-prompt.txt
#        /tmp/codex-review-add-foo-handler-prompt.txt
```

### 3. Dispatch IMPL seat

```
Task(
  subagent_type = "archon-task-implementor",
  run_in_background = True,
  prompt = "Validation Prompt: /tmp/codex-review-add-foo-handler-prompt.txt

  Read your prompt from:
  /tmp/codex-impl-add-foo-handler-prompt.txt

  Archon Project ID: <uuid>
  Archon Task ID: <uuid>"
)
```

Wait for the sub-agent's lean report. It will return:
- Files created / modified
- Lint status
- Path to its summary

### 4. Promote to review + dispatch REVIEW seat

```python
manage_task("update", task_id=task["id"], status="review", assignee="codex-review")
```

```
Task(
  subagent_type = "fork-delegator",
  prompt = """mode: structured
  prompt_file: /tmp/codex-review-add-foo-handler-prompt.txt
  slug: review-add-foo-handler
  cli: codex
  model: gpt-5.3-codex
  target_file: /tmp/codex-review-add-foo-handler-summary.md
  tool_label: archon-dual-fork-review"""
)
```

### 5. Render verdict

- Read the first 8 lines of `/tmp/codex-review-add-foo-handler-summary.md`
- Check `git status` → must be empty (exam integrity)
- On PASS: `manage_task(status=done, assignee=verified)`
- On FAIL: read `## Remediation` section, loop back to step 3 with fix context

---

## Pipelined — multiple tasks, two terminals always busy

**Pre-req:** tasks must be independent (no file overlap, no shared state).
Orchestrator detects this by intersecting each task's `files` list.

```
time →
  t0 ─ IMPL task A
  t1 ─ IMPL task A done ─ REVIEW task A + IMPL task B  (both forks running)
  t2 ─ REVIEW task A done ─ REVIEW task B + IMPL task C
  t3 ─ ...
```

Loop:
1. Pull N tasks with `find_tasks(status=todo, limit=3)`
2. Check pairwise file-overlap — drop any that conflict
3. Dispatch IMPL for task 0, wait for return
4. Dispatch REVIEW for task 0 AND IMPL for task 1 (both in background)
5. Whichever returns first, handle:
   - REVIEW done → verdict + Archon update
   - IMPL done → dispatch REVIEW for that task, dispatch IMPL for next
6. Continue until queue drained

Max two forks in flight simultaneously (one IMPL, one REVIEW). Don't try to
parallelize IMPL seats across tasks — that's a different pattern.

---

## Sandbox seat (rarely used on this project)

Between step 3 and step 4, if the task modifies runtime behavior (not just docs
or types):

```bash
# Check what sandbox tier is available
uv run .claude/skills/archon-dual-fork/scripts/preflight.py
# {"tier": "bwrap", ...}  ← Linux default
```

Dispatch `codex-delegator` sub-agent with a sandbox-routing prompt (see
codex-delegator Phase 7). On sandbox FAIL, skip REVIEW and loop back to fix.
On sandbox PASS, continue to REVIEW.

---

## Remediation — fix then re-run

On REVIEW FAIL:

```python
# 1. Extract remediation from review summary
with open("/tmp/codex-review-add-foo-handler-summary.md") as f:
    review = f.read()
remediation = extract_section(review, "## Remediation")

# 2. Write remediation to file for next IMPL prompt
with open("/tmp/remediation-add-foo-handler.md", "w") as f:
    f.write(remediation)

# 3. Update Archon
manage_task("update", task_id=task["id"], status="todo",
            task_order=95, assignee="codex-impl-r2")

# 4. Rebuild IMPL prompt with remediation context
# REVIEW prompt is unchanged — same exam.
```

```bash
uv run .claude/skills/archon-dual-fork/scripts/build_prompts.py \
  --task-json /tmp/task-add-foo.json \
  --attempt 2 \
  --remediation-file /tmp/remediation-add-foo-handler.md
```

5. Re-dispatch IMPL, then REVIEW (with unchanged review prompt file).

Hard-stop at attempt 3 → create sub-task, mark `user-escalated`.
