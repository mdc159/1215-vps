**First seven-day implementation checklist**

- **Day one**
  - Create separate Hermes profiles for `eng-ceo`, `research-ceo`, and `orchestrator-ceo`.
  - Run the Phase 0 resumability script on the Mac with built-in memory only.
  - Pin exact Hermes and adapter versions. ([github.com](https://github.com/NousResearch/hermes-agent/releases))

- **Day two**
  - Add explicit `--profile` in adapter `extraArgs` for one Mac-based Paperclip company.
  - Verify `persistSession` and `--resume` across five heartbeats.
  - Add absolute `cwd` and dedicated workspace root.

- **Day three**
  - Implement the Postgres alignment-log schema on the VPS.
  - Build `broadcast_publish`, `broadcast_replay`, and `broadcast_ack`.
  - Add local JSONL outbox and cursor files on the Mac.

- **Day four**
  - Stand up minimal Neo4j and Qdrant schemas.
  - Implement `artifact_register`, `kg_upsert`, and `corpus_add`.
  - Ingest one paper and one synthetic artifact summary.

- **Day five**
  - Run the Research Company Hindsight local admission test on the Mac.
  - Measure first-start latency, restart recovery, and recall reliability.
  - If it fails, prototype OpenViking immediately instead. ([hindsight.vectorize.io](https://hindsight.vectorize.io/developer/installation))

- **Day six**
  - On the Windows host, implement the first version of the localhost broker service.
  - Prove `submit_job`, `get_job`, and `cancel_job` for MATLAB or one equivalent tool.
  - Write artifact manifests and publish summaries only.

- **Day seven**
  - Add Langfuse trace taxonomy and redaction middleware.
  - Take the first cold backup of all profiles and outboxes.
  - Write and test the runbook for:
    - stale Paperclip lock cleanup,
    - provider disable/restore,
    - alignment-log replay after outage. ([github.com](https://github.com/paperclipai/paperclip/issues/2912))

This design is practical because it assumes today’s products as they actually exist: Paperclip as the company runtime, Hermes as the session and memory runtime, and the VPS stack as the durable organizational broker. It is also defensible because the critical cross-company continuity is pushed into explicit, replayable, provenance-bearing stores that remain readable even if any one provider has to be swapped out later. ([github.com](https://github.com/paperclipai/paperclip/blob/master/README.md))