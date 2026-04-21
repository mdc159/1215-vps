# 1215-vps

`1215-vps` is being rebuilt as a prototype-first, architecture-driven system.
The current design is documented in `docs/architecture/` and centers on:

- a shared continuity plane as system of record
- `n8n` as the trusted workflow nervous system
- Open WebUI as the primary human-facing shell
- Paperclip as the specialist orchestration surface
- Hermes as a host-native execution runtime behind a gateway boundary

The implementation strategy is:

1. build the **local prototype** as the first concrete local-node implementation
2. use that prototype to validate the continuity contracts and node pattern
3. promote the validated architecture into the hardened **VPS hub**

## Architecture Review Pack

Start with these documents:

- `docs/architecture/overview.md`
- `docs/architecture/service-catalog.md`
- `docs/architecture/network-port-map.md`
- `docs/architecture/runtime-flows.md`
- `docs/architecture/security-observability.md`
- `docs/architecture/inter-node-data-flow.md`
- `docs/architecture/implementation-roadmap.md`

## Repo Layout

- `modules/` contains upstream source references and submodules
- `docs/architecture/` contains the current blueprint and review pack
- `stack/topology/` contains repo-owned target and service manifests
- `stack/control/` contains the repo-owned CLI and control-plane tooling
- `bin/start-1215.py` is the repo-root entrypoint shim

## Current CLI

The new control project is scaffolded first so the repo has a working entrypoint
before container orchestration is implemented.

```bash
./bin/start-1215.py doctor
./bin/start-1215.py targets
./bin/start-1215.py services --target prototype-local
./bin/start-1215.py docs
```

These commands currently validate prerequisites and expose the new manifests.
They do not bring up services yet.

## Upstream References

- `modules/local-ai-packaged`
- `modules/hermes-agent`
- `modules/hermes-paperclip-adapter`
- `modules/hermes-agent-self-evolution`
- `modules/autoreason`
- `modules/paperclip`
- `modules/honcho`
- `modules/n8n-mcp`


• Committed.

  - Commit: e1a4b21
  - Includes:
      - stack/prototype-local/scripts/setup_hermes_honcho_paperclip.py (new)
      - stack/prototype-local/README.md update
  - The script is functioning; I ran it successfully and it verified:
      - Honcho health on 127.0.0.1:18000
      - Paperclip health on 127.0.0.1:3100/api/health
      - Hermes↔Honcho cross-session memory smoke test (write/read token)


  python3 stack/prototype-local/scripts/setup_hermes_honcho_paperclip.py --model openai/gpt-5

  (or Sonnet/Gemini/OpenRouter model IDs you prefer).