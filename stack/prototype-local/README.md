# prototype-local

`prototype-local` is the first runnable local-node implementation for the 1215
architecture. It is not a throwaway dev stack. It exists to validate the
shared continuity contracts, localhost-only exposure model, and the service mix
before hardening the VPS hub.

## Scope of the first substrate slice

This initial compose focuses on the foundational local services:

- Postgres
- Valkey
- MinIO
- Qdrant
- Neo4j
- ClickHouse
- Langfuse
- Open WebUI
- n8n

It does **not** yet include:

- the broker API/workers
- Paperclip
- Hermes gateway
- Honcho
- `n8n-mcp`

Those are added after the substrate is validated.

## Bring-up

```bash
docker compose -f stack/prototype-local/docker-compose.substrate.yml up -d
docker compose -f stack/prototype-local/docker-compose.substrate.yml ps
```

All ports bind to `127.0.0.1` only in this first slice.

## Notes

- The compose file uses prototype-safe defaults so it can be rendered without a
  hand-maintained `.env`.
- Do not reuse these defaults for a shared or public deployment.
