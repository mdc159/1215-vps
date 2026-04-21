Install self-hosted Honcho memory for Hermes Agent.

Context:
Hermes is already installed on this VPS. n8n and Flowise MCP servers are already connected. Tailscale is already available. CBass already includes Docker Compose, Caddy, Supabase/Postgres with pgvector, Ollama, n8n, Flowise, Open WebUI, Qdrant, Neo4j, Langfuse, Redis/Valkey, MinIO, and SearXNG.

Primary rule:
Reuse existing CBass infrastructure. Do not add duplicate Postgres, vector DB, reverse proxy, or observability services unless inspection proves reuse is unsafe.

Security rule:
Do not expose Honcho publicly during the first install. Keep Honcho private using localhost, Docker-internal networking, or Tailscale. Do not add a public Caddy route. Do not use Tailscale Funnel.

Preferred access paths:
- Hermes on same VPS host: HONCHO_BASE_URL=http://127.0.0.1:8000
- Hermes in Docker: HONCHO_BASE_URL=http://honcho:8000
- Trusted remote access only if needed: use Tailscale tailnet IP, MagicDNS, or Tailscale Serve

Database plan:
Use the existing CBass Supabase/Postgres service if safe. Create a dedicated Honcho database and preferably a dedicated Honcho DB user. Enable required extensions in the Honcho database:

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

Use a Postgres connection string like:

DB_CONNECTION_URI=postgresql+psycopg://honcho_app:${HONCHO_DB_PASSWORD}@db:5432/honcho

Use the actual DB service name discovered from Docker Compose. Do not use Supabase service-role keys as Honcho DB credentials. Do not use transaction pooling for initial migrations unless Honcho docs explicitly confirm it is safe.

Before editing:
1. Identify repo path.
2. Inspect Docker Compose files, networks, service names, ports, and .env variable patterns.
3. Render current Compose config.
4. Back up docker-compose.yml, .env, and Caddyfile if present.

Use commands similar to:

docker compose -p localai ps
docker compose -p localai config > /tmp/cbass.compose.before-honcho.yml
docker network ls

Back up before changes:

cp docker-compose.yml docker-compose.yml.bak.$(date +%Y%m%d-%H%M%S)
cp .env .env.bak.$(date +%Y%m%d-%H%M%S)
[ -f Caddyfile ] && cp Caddyfile Caddyfile.bak.$(date +%Y%m%d-%H%M%S)

Implementation:
1. Inspect current official Honcho self-hosting docs/repo before choosing exact image/build method.
2. Add Honcho as a private service in the existing Compose project.
3. Prefer Docker-internal exposure with expose: ["8000"].
4. If host access is needed, bind only to localhost: "127.0.0.1:8000:8000".
5. Do not use "8000:8000" on all interfaces.
6. Configure Honcho to use the dedicated Honcho database.
7. Configure Hermes with the correct HONCHO_BASE_URL.
8. Validate cross-session memory persistence.

Do not:
- print secrets
- commit .env
- paste raw credentials into markdown
- expose Honcho publicly
- use Tailscale Funnel
- create duplicate Postgres unless necessary
- modify unrelated CBass services
- store secrets in Hermes memory, Honcho memory, Langfuse, n8n notes, Flowise prompts, Qdrant, Neo4j, or project docs

Validation:
Run health checks and memory checks:

docker compose -p localai up -d honcho
docker compose -p localai logs honcho --tail=100
curl http://127.0.0.1:8000/health
hermes honcho status
hermes memory status
hermes doctor

Then test memory:
1. Tell Hermes a harmless durable fact.
2. Start a new Hermes session.
3. Verify the fact is recalled.
4. Test a fake secret string such as sk-test-DO-NOT-STORE-12345.
5. Verify the fake secret does not appear in Hermes memory, Honcho logs, Langfuse traces, n8n, Flowise, Qdrant, Neo4j, or project files.

Stop and ask for review if:
- database credentials are unclear
- pgvector or pg_trgm cannot be enabled
- Honcho migrations fail
- Honcho requires public exposure
- secrets appear in logs
- changes would destabilize unrelated CBass services
- Hermes can only reach Honcho through a public URL

Return:
1. files changed
2. database and user created
3. Honcho base URL selected
4. whether access is localhost, Docker-internal, or Tailscale
5. health-check output with secrets redacted
6. Hermes status output with secrets redacted
7. memory persistence test result
8. fake-secret leakage test result
9. rollback steps