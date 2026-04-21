---
name: broadcast-ack
description: Advance a provider checkpoint in the 1215 broker (read-before-write, monotonic). Use this after processing a batch of events from broadcast-read-feed so a later resume starts exactly where you left off. Supports --read to inspect the current cursor.
version: 1.0.0
metadata:
  hermes:
    tags: [continuity-plane, broker, checkpoints, replay]
    related_skills: [broadcast-publish, broadcast-read-feed]
---

# broadcast_ack — advance a provider checkpoint

## When to use

After consuming a batch of events via `broadcast-read-feed`, ack the
highest `event_seq` you processed so the next resume doesn't reprocess
them:

```bash
# 1. Find where we left off
cursor=$(python3 .../broadcast-ack/scripts/broadcast_ack.py --read \
  --provider hermes-ceo \
  --checkpoint-kind replay-cursor)

# 2. Read newer events
python3 .../broadcast-read-feed/scripts/broadcast_read_feed.py \
  --after-seq "${cursor:-0}" --limit 100 > /tmp/batch.json

# 3. Process them ... then ack the highest event_seq seen
highest=$(jq '.events | max_by(.event_seq) | .event_seq' /tmp/batch.json)
python3 scripts/broadcast_ack.py \
  --provider hermes-ceo \
  --checkpoint-kind replay-cursor \
  --cursor-value "$highest"
```

## Contract

- `(provider_name, node_id, checkpoint_kind)` is the composite key.
  Each provider+node+kind triple has exactly one cursor row.
- `checkpoint_kind` must exist in `broker.checkpoint_kinds`
  (`publish-outbox`, `replay-cursor`, `provider-sync`).
- **Monotonic by default.** If the existing cursor and the new value
  both parse as integers (the common case — `event_seq`), rewinding is
  refused with exit `4`. Pass `--force` to override (e.g. operator
  intervention after a broken replay).
- `--read` prints the current `cursor_value` to stdout (empty line if
  no row exists) so shell pipelines can seed the initial cursor.
- Broker FK-rejects unknown `node_id` — call `broadcast_publish` or the
  gateway's run lifecycle first, so the node row exists.

## Exit codes

- `0` — wrote (or read) successfully.
- `2` — broker 4xx/5xx rejected the write.
- `3` — broker unreachable.
- `4` — monotonic check failed (rewind refused; pass `--force`).

## Defaults

- `--broker-url` ← `$BROKER_URL`, else `http://127.0.0.1:8090`
- `--node-id` ← `$HERMES_NODE_ID`, else `ceo-orchestrator`
