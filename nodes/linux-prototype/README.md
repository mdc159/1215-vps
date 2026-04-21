# linux-prototype

The single Linux workstation node that hosts this repository. It plays the
prototype role for the eventual VPS topology: it runs the full substrate
(Postgres, Valkey, MinIO, Qdrant, Neo4j, ClickHouse, Langfuse), the human
and agent surfaces (Open WebUI, Paperclip, n8n, n8n-mcp), the specialized
CPU media worker (ComfyUI), and — as Phases B–E land — the host-native
Hermes stack (Honcho systemd unit, `hermes-gateway` daemon, and the
`orchestrator-ceo` Hermes profile). Its role string is
`core,media-cpu,tools`: it owns the shared continuity plane and common
contracts, provides CPU-mode media generation as the smoke-test surface,
and carries the authoring / debugging tooling (MCP, n8n-mcp). GPU-heavy
and VPS-hub roles are deliberately not enabled here.
