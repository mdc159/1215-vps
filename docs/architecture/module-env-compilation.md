# Module Env Compilation

This is a grounded compilation of env examples found under [modules](/mnt/data/Documents/repos/1215-vps/modules), based on the git submodules declared in [.gitmodules](/mnt/data/Documents/repos/1215-vps/.gitmodules).

## Sources

- `modules/hermes-agent/.env.example`
- `modules/honcho/.env.template`
- `modules/local-ai-packaged/.env.example`
- `modules/n8n-mcp/.env.example`
- `modules/n8n-mcp/.env.docker`
- `modules/n8n-mcp/.env.n8n.example`
- `modules/paperclip/.env.example`

## Per Module

### `hermes-agent`

Source: [modules/hermes-agent/.env.example](/mnt/data/Documents/repos/1215-vps/modules/hermes-agent/.env.example)

Keys:
- `TERMINAL_MODAL_IMAGE`
- `TERMINAL_TIMEOUT`
- `TERMINAL_LIFETIME_SECONDS`
- `BROWSERBASE_PROXIES`
- `BROWSERBASE_ADVANCED_STEALTH`
- `BROWSER_SESSION_TIMEOUT`
- `BROWSER_INACTIVITY_TIMEOUT`
- `WEB_TOOLS_DEBUG`
- `VISION_TOOLS_DEBUG`
- `MOA_TOOLS_DEBUG`
- `IMAGE_TOOLS_DEBUG`

Notes:
- Most provider API keys in this example are commented out rather than active assignments.
- The repo-level prototype will still need user/provider keys such as `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, and optional web/image tool keys because Hermes supports them even though they are commented in the example.

### `honcho`

Source: [modules/honcho/.env.template](/mnt/data/Documents/repos/1215-vps/modules/honcho/.env.template)

Keys:
- `LOG_LEVEL`
- `DB_CONNECTION_URI`
- `AUTH_USE_AUTH`
- `LLM_OPENAI_COMPATIBLE_BASE_URL`
- `LLM_OPENAI_COMPATIBLE_API_KEY`
- `LLM_EMBEDDING_PROVIDER`
- `DERIVER_PROVIDER`
- `DERIVER_MODEL`
- `SUMMARY_PROVIDER`
- `SUMMARY_MODEL`
- `DREAM_PROVIDER`
- `DREAM_MODEL`
- `DREAM_DEDUCTION_MODEL`
- `DREAM_INDUCTION_MODEL`
- `VECTOR_STORE_TYPE`
- `VECTOR_STORE_MIGRATED`

Common commented-but-important Honcho settings:
- `LANGFUSE_HOST`
- `LANGFUSE_PUBLIC_KEY`
- `AUTH_JWT_SECRET`
- `WEBHOOK_SECRET`

Notes:
- Honcho’s upstream module expects exact names like `DB_CONNECTION_URI`.
- Our architecture docs also define repo-level derived variables like `HONCHO_DB_PASSWORD` and `HONCHO_DB_CONNECTION_URI`. Those are useful as operator vars even though the upstream container expects `DB_CONNECTION_URI`.

### `local-ai-packaged`

Source: [modules/local-ai-packaged/.env.example](/mnt/data/Documents/repos/1215-vps/modules/local-ai-packaged/.env.example)

Primary infra keys:
- `N8N_ENCRYPTION_KEY`
- `N8N_USER_MANAGEMENT_JWT_SECRET`
- `POSTGRES_PASSWORD`
- `JWT_SECRET`
- `ANON_KEY`
- `SERVICE_ROLE_KEY`
- `DASHBOARD_USERNAME`
- `DASHBOARD_PASSWORD`
- `POOLER_TENANT_ID`
- `GLOBAL_S3_BUCKET`
- `REGION`
- `STORAGE_TENANT_ID`
- `S3_PROTOCOL_ACCESS_KEY_ID`
- `S3_PROTOCOL_ACCESS_KEY_SECRET`
- `NEO4J_AUTH`
- `CLICKHOUSE_PASSWORD`
- `MINIO_ROOT_PASSWORD`
- `LANGFUSE_SALT`
- `NEXTAUTH_SECRET`
- `ENCRYPTION_KEY`

Secondary service/config keys:
- `POSTGRES_HOST`
- `POSTGRES_DB`
- `POSTGRES_PORT`
- `POSTGRES_USER`
- `POOLER_PROXY_PORT_TRANSACTION`
- `POOLER_DEFAULT_POOL_SIZE`
- `POOLER_MAX_CLIENT_CONN`
- `SECRET_KEY_BASE`
- `VAULT_ENC_KEY`
- `POOLER_DB_POOL_SIZE`
- `KONG_HTTP_PORT`
- `KONG_HTTPS_PORT`
- `PGRST_DB_SCHEMAS`
- `SITE_URL`
- `ADDITIONAL_REDIRECT_URLS`
- `JWT_EXPIRY`
- `DISABLE_SIGNUP`
- `API_EXTERNAL_URL`
- `MAILER_URLPATHS_CONFIRMATION`
- `MAILER_URLPATHS_INVITE`
- `MAILER_URLPATHS_RECOVERY`
- `MAILER_URLPATHS_EMAIL_CHANGE`
- `ENABLE_EMAIL_SIGNUP`
- `ENABLE_EMAIL_AUTOCONFIRM`
- `SMTP_ADMIN_EMAIL`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASS`
- `SMTP_SENDER_NAME`
- `ENABLE_ANONYMOUS_USERS`
- `ENABLE_PHONE_SIGNUP`
- `ENABLE_PHONE_AUTOCONFIRM`
- `STUDIO_DEFAULT_ORGANIZATION`
- `STUDIO_DEFAULT_PROJECT`
- `STUDIO_PORT`
- `SUPABASE_PUBLIC_URL`
- `IMGPROXY_ENABLE_WEBP_DETECTION`
- `OPENAI_API_KEY`
- `FUNCTIONS_VERIFY_JWT`
- `LOGFLARE_PUBLIC_ACCESS_TOKEN`
- `LOGFLARE_PRIVATE_ACCESS_TOKEN`
- `DOCKER_SOCKET_LOCATION`
- `GOOGLE_PROJECT_ID`
- `GOOGLE_PROJECT_NUMBER`

Notes:
- This module is the source for many of the shared substrate secrets already used by `prototype-local`.
- It also introduces later-phase Supabase and edge keys that are not needed for the current prototype.

### `n8n-mcp`

Sources:
- [modules/n8n-mcp/.env.example](/mnt/data/Documents/repos/1215-vps/modules/n8n-mcp/.env.example)
- [modules/n8n-mcp/.env.docker](/mnt/data/Documents/repos/1215-vps/modules/n8n-mcp/.env.docker)
- [modules/n8n-mcp/.env.n8n.example](/mnt/data/Documents/repos/1215-vps/modules/n8n-mcp/.env.n8n.example)

Core keys:
- `AUTH_TOKEN`
- `NODE_DB_PATH`
- `NODE_ENV`
- `LOG_LEVEL`
- `MCP_LOG_LEVEL`
- `MCP_MODE`
- `PORT`
- `HOST`
- `REBUILD_ON_START`

Optional management / integration keys:
- `N8N_API_URL`
- `N8N_API_KEY`
- `N8N_API_TIMEOUT`
- `N8N_API_MAX_RETRIES`
- `ENABLE_MULTI_TENANT`

Related n8n-side keys from `.env.n8n.example`:
- `N8N_BASIC_AUTH_ACTIVE`
- `N8N_BASIC_AUTH_USER`
- `N8N_BASIC_AUTH_PASSWORD`
- `N8N_HOST`
- `N8N_PORT`
- `N8N_PROTOCOL`
- `N8N_WEBHOOK_URL`
- `N8N_ENCRYPTION_KEY`
- `MCP_PORT`
- `MCP_AUTH_TOKEN`
- `GITHUB_REPOSITORY`
- `VERSION`

Notes:
- In this repo, `prototype-local` wraps these through repo-level names like `N8N_MCP_AUTH_TOKEN`, `N8N_MCP_LOG_LEVEL`, and `N8N_MCP_REBUILD_ON_START`.

### `paperclip`

Source: [modules/paperclip/.env.example](/mnt/data/Documents/repos/1215-vps/modules/paperclip/.env.example)

Keys:
- `DATABASE_URL`
- `PORT`
- `SERVE_UI`
- `BETTER_AUTH_SECRET`

Additional keys used in Paperclip’s Docker compose:
- `PAPERCLIP_PUBLIC_URL`
- `PAPERCLIP_DEPLOYMENT_MODE`
- `PAPERCLIP_DEPLOYMENT_EXPOSURE`

Notes:
- The upstream env uses generic names like `DATABASE_URL` and `PORT`.
- For the repo-owned prototype, it is safer to track repo-scoped Paperclip values in our shared `.env` without relying on those generic names unless we adopt the upstream compose directly.

## What Belongs In `stack/prototype-local/.env`

### Keep populated now

These are already part of the working local substrate and should stay authoritative in `stack/prototype-local/.env`:
- `POSTGRES_PASSWORD`
- `MINIO_ROOT_PASSWORD`
- `CLICKHOUSE_PASSWORD`
- `LANGFUSE_DATABASE_NAME`
- `LANGFUSE_SALT`
- `ENCRYPTION_KEY`
- `NEXTAUTH_SECRET`
- `N8N_ENCRYPTION_KEY`
- `N8N_USER_MANAGEMENT_JWT_SECRET`
- `N8N_API_KEY`
- `N8N_MCP_AUTH_TOKEN`
- `N8N_MCP_LOG_LEVEL`
- `N8N_MCP_REBUILD_ON_START`
- `N8N_MCP_TELEMETRY_DISABLED`
- `OPEN_WEBUI_ADMIN_EMAIL`
- `OPEN_WEBUI_ADMIN_NAME`
- `OPEN_WEBUI_ADMIN_PASSWORD`
- `OPEN_WEBUI_IMAGE`
- `COMFYUI_IMAGE`
- `COMFYUI_USER_ID`
- `COMFYUI_GROUP_ID`
- `NEO4J_AUTH`

### Add now for next prototype work

These are the next useful operator vars for planned Honcho / Paperclip / Hermes work:
- `HONCHO_DB_PASSWORD`
- `HONCHO_DB_CONNECTION_URI`
- `HONCHO_CACHE_URL`
- `HONCHO_CACHE_ENABLED`
- `HONCHO_BASE_URL`
- `HONCHO_LLM_PROVIDER`
- `HONCHO_LLM_BASE_URL`
- `HONCHO_LLM_MODEL`
- `HONCHO_LLM_API_KEY`
- `HONCHO_EMBEDDING_PROVIDER`
- `HONCHO_EMBEDDING_BASE_URL`
- `HONCHO_EMBEDDING_MODEL`
- `HONCHO_EMBEDDING_API_KEY`
- `BROKER_APP_PASSWORD`
- `LANGFUSE_HOST`
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`
- `BETTER_AUTH_SECRET`
- `PAPERCLIP_PUBLIC_URL`
- `PAPERCLIP_DEPLOYMENT_MODE`
- `PAPERCLIP_DEPLOYMENT_EXPOSURE`
- `PAPERCLIP_API_URL`
- `PAPERCLIP_BROWSER_ORIGIN`
- `OPENROUTER_API_KEY`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GOOGLE_API_KEY`

### Keep blank unless and until needed

These are legitimate future keys, but they are not necessary to move the current prototype forward today:
- Full Supabase stack keys such as `JWT_SECRET`, `ANON_KEY`, `SERVICE_ROLE_KEY`, `DASHBOARD_PASSWORD`, `POOLER_TENANT_ID`
- Edge hostnames such as `N8N_HOSTNAME`, `WEBUI_HOSTNAME`, `LANGFUSE_HOSTNAME`, `NEO4J_HOSTNAME`, `FLOWISE_HOSTNAME`, `SUPABASE_HOSTNAME`, `OLLAMA_HOSTNAME`, `SEARXNG_HOSTNAME`
- Optional Hermes web/search/media tool keys such as `EXA_API_KEY`, `PARALLEL_API_KEY`, `FIRECRAWL_API_KEY`, `FAL_KEY`

