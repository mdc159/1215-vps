# archon-dual-fork — Field Notes

Append-only log of gripes, surprises, and things that felt wrong during live runs.
One line per entry. Tag `[breaking]` if a run broke in a new way.

Format:
```
YYYY-MM-DD | SEAT | slug | <what felt wrong>
```

Mined during skill maintenance — not analyzed in-flight.

---

<!-- entries below -->
2026-04-20 | REVIEW | t3-secrets-generate-hex-pure-f | [breaking] REVIEW prompt's `ID_MISMATCH` guard requires the plan file header to contain the Archon Project ID, but plan files written before the Archon project exists won't have one. First REVIEW fork halted at the guard before grading any AC. Workaround: orchestrator stamps `**Archon Project ID:** <uuid>` into the plan header and commits before dispatching REVIEW. Real fix candidates: (a) make `build_prompts.py` auto-stamp the plan, (b) soften the guard to a warning when the ID is missing entirely (vs present-but-mismatched), (c) document the requirement in the skill's "When to Use" section.
