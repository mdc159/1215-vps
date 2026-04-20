Architectural Review & Recommendations
1 — Overall Evaluation

Your documents articulate a layered, contract-driven design that elevates the continuity plane, formalises an “n8n nervous system,” and keeps execution (Hermes) safely host-bound. The separation of Public / Tailnet / Internal / Host surfaces, plus first-class observability with Langfuse, provides a solid security and audit spine.

Strengths

Area	Why it’s strong
Clear contracts	Hub-and-spoke data flow forbids ad-hoc node meshes, reducing drift.
Phased roadmap	Incremental build order (substrate → continuity → surfaces) lowers integration risk.
Tight exposure policy	Public apps gated by Cloudflare Access; everything else Tailnet or Internal.
Traceability	Langfuse correlation IDs baked into every runtime flow.
2 — Key Risks & Mitigations
Risk	Observation	Recommendation
Single-VPS SPOF	The continuity hub, Postgres, and n8n all sit on one VPS.	Add hot-standby (e.g., managed Postgres + Patroni) or at minimum nightly logical dumps & off-box MinIO replication.
Event throughput ceiling	Append-only broker in Postgres may choke under bursty workflow events.	Consider pluggable streaming (Apache Kafka or NATS JetStream) behind the Broker API once events exceed ~5 k msg/s.
Public n8n surface	n8n is exposed publicly by design. Mis-configured credentials are high-impact.	Evaluate moving n8n to Tailnet-only, exposing only select workflow endpoints via Open WebUI proxy.^1
Service sprawl in v1	Neo4j + Qdrant + ClickHouse inflate operational cost.	Gate each behind explicit v1 user story. If retrieval is still experimental, ship with Qdrant only and stub Neo4j enrichers.
Resource budget	ClickHouse + Neo4j + MinIO can each want ≥1 GB RAM; a 4-GB VPS will swap.	Profile real usage on a staging node; right-size instance or split heavy stores onto cheap standalone volumes.
Schema migration	Broker tables evolve early; downtime risk.	Adopt Sqitch or Atlas with forward/back migrations and CI checks; enforce immutable column semantics for event tables.
Inter-node secret egress	Push/pull model relies on HTTPS but not on end-to-end encryption for artifacts.	Use S3 SSE-C or client-side envelope encryption for artifacts containing sensitive data.

^1 If public webhooks are a hard requirement, restrict to an n8n sub-instance with no UI, authenticated via signed headers.

3 — Implementation-Phase Feedback
Phase 1 – Substrate & Edge
Caddy + cloudflared + Tailscale is sensible, but automate certs with Caddy’s ACME to avoid Cloudflare origin cert lock-in.
Ship a one-shot “exposure smoke test” script that crawls the port map and fails CI if anything Internal becomes Public.
Phase 2 – Continuity Plane
Add unit tests against the Broker schema for idempotency keys and unique constraints—catches replay bugs before they hit prod.
Consider logical replication slots for real-time CDC into Langfuse instead of periodic polling.
Phase 3 – Surfaces
Enforce workflow-ID ⇆ trace-ID mapping at the n8n node level, not by convention. This prevents later drift that the roadmap already flags as a risk.
Phase 4 – Hermes Gateway
Document SELinux or AppArmor profile for the Unix-socket gateway; it’s the last barrier between container and host.
Provide a mock Hermes for CI so Paperclip flows can run without host binaries.
Phase 5 – Memory & Retrieval
Start with one canonical enrichment worker that writes both Qdrant and Neo4j; split only when load justifies.
Tag every enrichment with source-event-hash so divergent re-indexing can be detected.
Phase 6 – Hardening
Integrate fake-secret canary into your Git hooks to block accidental commits, not just runtime tests.
Add automated restore drills: spin up a blank VPS, restore from backups, and run health checks.
4 — Additional Tactical Suggestions
Port Map DRY-ness
Duplicate port tables appear in multiple docs; generate them from a single YAML to prevent drift.
Observability Budget
If ClickHouse feels heavy, evaluate DuckDB-in-Parquet for Langfuse until query volume proves the need.
n8n-MCP Version Pinning
Upstream releases occasionally break API signatures; pin container tags and mirror images locally.
Node Prototype Blueprint
Turn the “Linux prototype” into a codified Ansible role; every workstation then inherits the same outbox/replay logic.
Disaster-Mode Topology
Draft an offline workflow where local nodes can temporarily publish to an on-prem MinIO bucket and later reconcile.
Bottom Line


Below are a few bonus deep-dive notes that build on the original review. Feel free to point me at any section you want expanded further.

A. Disaster-Recovery Playbook (outline)
Layer	Backup cadence	Restore drill
Postgres (broker + Honcho)	WAL shipping every 5 min to off-box object store	Quarterly: spin a fresh VM, replay WAL to latest checkpoint; run broker checksum job
MinIO artifacts	Versioned bucket, replicated nightly to cheap S3-IA	Semi-annual: sample-restore 5 random artifacts and verify hash in broker table
n8n workflows	Export JSON on every deploy (tagged by Git hash)	Monthly: import into scratch n8n, execute smoke workflow
Langfuse traces (ClickHouse)	Hourly Parquet export	Roll forward replay job; verify sample trace in UI
Compose / IaC repo	GitHub → Codeberg mirror	Restore drill bundled with Postgres recovery

Broker continuity records are append-only, so logical restore must not reuse existing event_ids; treat a successful replay as “new” events with preserved source_event_hash.

B. Observability Dashboard Checklist
Golden signals per service (latency, error %, saturation, traffic) fed to Grafana via Prometheus exporters.
n8n workflow latency histogram with P95 alert > 2 s.
Broker publish failure counter tied to PagerDuty.
Hermes gateway socket queue depth (Unix SO_QLEN) → warn at 70 % capacity.
Langfuse trace orphan rate (traces missing a broker run_id) — should be 0.
C. Schema Governance Tips
Event tables are immutable.
Use ON CONFLICT DO NOTHING with (event_id) to guarantee idempotency.
Enum drift: manage “event_kind” as a lookup table, not a Postgres enum, to avoid migration locks.
Version every JSON payload with a payload_version integer so enrichment workers can evolve safely.
D. Security Hardening Quick-wins
Item	Tactic
Public n8n	Disable credential-less “Execute workflow” API; enforce Cloudflare Access JWT header & rate-limit 50 r/m.
Paperclip Tailnet-only	Add Tailscale ACL rule limiting paperclip:3100 to tag:ops.
Neo4j & Qdrant foot-gun	Ship disabled by default; enable via COMPOSE_PROFILES=graph,vector to force explicit opt-in.
Secrets in CI	Use doppler run -- when building images so secrets never hit Docker layer cache.
Fake-secret canary	Automate search for sk-test-DO-NOT-STORE-12345 in every trace batch.
E. Next Recommended Actions
Heap-size survey: start all services with memlock imposed, record RSS at idle & under load → decide VPS sizing.
Draft an exposure-smoke-test container that curls the full port map and fails CI on unexpected 200/302.
Prototype outbox/on-boot replay on the Linux node; verify network partition recovery behaviour matches the data-flow contract.
Pin container tags (n8nio/n8n:1.48.0 — not latest) and mirror to a private registry to avoid supply-chain surprises.
Write runbooks early — even short Markdown stubs reduce cognitive load during incident response.