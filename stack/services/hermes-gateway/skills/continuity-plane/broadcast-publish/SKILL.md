---
name: broadcast-publish
description: Publish an event to the 1215 continuity-plane broker. Use this to announce memory writes, run milestones, or any cross-node signal that other providers (Paperclip, n8n, replay) should observe. Idempotent on retry.
version: 1.0.0
metadata:
  hermes:
    tags: [continuity-plane, broker, events, broadcast]
    related_skills: [broadcast-read-feed, broadcast-ack, artifact-publish]
---

# broadcast_publish — publish a continuity-plane event

## When to use

Reach for this skill whenever the CEO produces a signal that **something
outside this process** should react to:

- `memory.published` — I just wrote a memory worth replaying.
- `artifact.registered` — I put a file in MinIO; register the reference
  (usually emitted by `artifact-publish` for you, not by hand).
- `workflow.started` / `workflow.completed` — a multi-turn plan
  transitioned state.
- Any node-local event that downstream consumers (replay, dashboards,
  other agents) read from the broker feed.

Do **not** use this skill for `run.created` / `run.started` /
`run.completed` — those are emitted by the hermes-gateway around the
run's lifecycle and publishing them by hand will collide on
`(node_id, idempotency_key)`.

## Contract

- `event_type` must exist in `broker.event_types` (see
  `stack/sql/broker/001_core.sql`). Unknown types 4xx.
- Retrying with the same `idempotency_key` returns the originally
  stored event. Scripts derive a stable key automatically from
  `(event_type, run_id|session_id, sha256(payload))`; override it
  only when you need to force a new row for the same payload.
- `payload_json` must be a JSON object (not an array or scalar).
- The broker auto-stamps `recorded_at`; `occurred_at` defaults to now
  in UTC unless you override it.

## How to run

```bash
# Minimal — announce a memory write scoped to the current run
python3 scripts/broadcast_publish.py \
  --event-type memory.published \
  --payload '{"summary":"CEO aligned on Q2 OKRs","source":"hermes-ceo"}'

# Full form with explicit scope
python3 scripts/broadcast_publish.py \
  --event-type workflow.completed \
  --payload @/tmp/workflow-output.json \
  --run-id r-2026-04-21-0001 \
  --session-id ceo-daily-standup \
  --metadata '{"latency_ms":4213}'
```

The script prints the broker's response row as JSON on stdout. Non-zero
exit codes: `2` = broker rejected, `3` = broker unreachable.

## Defaults

- `--broker-url` ← `$BROKER_URL`, else `http://127.0.0.1:8090`
- `--node-id` ← `$HERMES_NODE_ID`, else `ceo-orchestrator`
- `--session-id` ← `$HERMES_SESSION_ID`
- `--run-id` ← `$HERMES_RUN_ID`

These match the env the hermes-gateway injects into spawned runs.
