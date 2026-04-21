---
name: broadcast-read-feed
description: Read events from the 1215 continuity-plane broker, with filters (event_type, session_id, run_id, node_id, after_seq). Use this to inspect recent cross-node activity or to drive a replay-from-cursor loop.
version: 1.0.0
metadata:
  hermes:
    tags: [continuity-plane, broker, events, replay]
    related_skills: [broadcast-publish, broadcast-ack]
---

# broadcast_read_feed — read the broker event feed

## When to use

Two common patterns:

1. **Inspect recent activity** — "what's been published in this run?":
   ```bash
   python3 scripts/broadcast_read_feed.py --run-id r-2026-04-21-0001
   ```
2. **Replay from a cursor** — drive an incremental processing loop:
   ```bash
   # Find the last event this provider acknowledged
   cursor=$(python3 .../broadcast-ack/scripts/broadcast_ack.py --read --provider hermes-ceo ...)
   # Read everything newer than that
   python3 scripts/broadcast_read_feed.py --after-seq "$cursor" --event-type memory.published
   # ...process each event, then call broadcast_ack with the last seq
   ```

## Contract

- All filters are **conjunctive**. Passing
  `--event-type memory.published --run-id r-1` returns only events
  matching **both**.
- Results are ordered `event_seq DESC` (newest first). If you pass
  `--after-seq N` you're asking for `event_seq > N`, and the page is
  still newest-first, so sort ascending downstream if you need
  chronological replay.
- Broker caps `--limit` at 500.

## Output

Raw JSON envelope:

```json
{"events": [{"event_seq": 42, "event_type": "memory.published", ...}, ...], "count": 42}
```

Exit `2` on broker-side validation, `3` on connectivity failure.

## Defaults

- `--broker-url` ← `$BROKER_URL`, else `http://127.0.0.1:8090`
- No default for the filter flags — omit to disable that filter.
