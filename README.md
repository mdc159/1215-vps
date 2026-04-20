# 1215-vps

https://github.com/coleam00/local-ai-packaged.git
https://github.com/NousResearch/hermes-agent.git
https://github.com/NousResearch/hermes-paperclip-adapter.git
https://github.com/NousResearch/hermes-agent-self-evolution.git
https://github.com/NousResearch/autoreason.git
https://github.com/paperclipai/paperclip.git
https://github.com/plastic-labs/honcho.git
https://github.com/czlonkowski/n8n-mcp.git
https://github.com/czlonkowski/n8n-mcp.git

## Bring-up (Phase 1 - foundation)

Phase 1 brings up the data plane: Supabase, Langfuse data services, Qdrant,
Neo4j, Redis, and MinIO, then initializes the Honcho database and broker
schema.

Prerequisites: Docker Engine with Compose v2, `uv`, and a checkout with
submodules initialized. The Local AI Package upstream also expects its
`supabase/docker/` tree to exist before `up` can succeed.

```bash
# Seed stack/env/.env from the example and generate any missing secrets.
cp stack/env/.env.example stack/env/.env
./bin/start-1215.py check

# Bring up the Phase 1 data plane.
./bin/start-1215.py up --first-boot
```

On success, the data plane is healthy, the `honcho` database exists with the
`vector` and `pg_trgm` extensions, the `broker` schema contains the
`alignment_log` and `artifact_manifests` tables, and MinIO exposes the
`langfuse`, `n8n`, and `artifacts` buckets.

Phase 1 does not include the self-hosted Honcho services (Plan 2), the Hermes
gateway and Paperclip orchestrator (Plan 3), `n8n-mcp` and full Langfuse wiring
(Plan 4), or the edge/public exposure layer (Plan 5).

```bash
cd stack/control
uv run pytest
uv run pytest -m integration
```
