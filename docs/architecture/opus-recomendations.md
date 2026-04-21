Architecture recommendations
1. Make "one shared Postgres" a Phase 0, not Phase B
Phase A's "tidy foundations" did image pinning and manifest cleanup, but left per-service Postgres containers in place (Honcho had its own 1215-honcho-pg). I then had to rip that out in Phase B. In hindsight, the substrate should have been one Postgres, one MinIO, one Clickhouse from the very first compose up — with postgres-bootstrap creating all the needed databases and extensions (pgvector, pg_trgm, whatever's next) on day one.

The current design already landed here; it just took a phase of churn to get there. A future phased plan should state "substrate services are shared across all components" as an invariant in Phase A.

2. The broker should have been Phase 0
Right now the broker's schema evolved alongside the clients that used it (gateway in D, skills in F, Langfuse stamping in G). Each phase added columns/indices to it. The broker is the single source of truth — everything else (Langfuse, logs, file state) is a downstream cache. Building it first, with its full schema frozen, would have made the later phases cleaner because I could have leaned on it harder earlier.

Concretely: events, runs, sessions, nodes, artifacts, checkpoints, and the metadata_json JSONB column should all be committed before Phase A closes.

3. Canary-at-birth, not canary-check-later
The canary leak sweep is a Phase H smoke check. But the canary string itself was only introduced to test skills in Phase F. If every phase's acceptance had planted a unique canary and asserted its containment, we'd have found the cp -r leak at Phase C, not F. Pattern to adopt:

canary := profile_name + "-" + phase_letter + "-" + ULID
Each phase plants its own canary and leaves it in place. The final sweep becomes a multi-canary grep.

4. Replace "host-native systemd units" with a single process supervisor
The split between docker-compose (substrate) and systemctl --user (gateway, honcho, honcho-deriver) is the single biggest source of "which layer do I restart?" cognitive load. Three of the Phase H bugs (unit discovery path, stale socket, service-not-adopted-by-systemctl-enable) all come from this split.

Options, in order of effort:

Low effort: keep systemd, but wrap everything behind ./bin/1215 {up,down,restart} (already done in H) so the split is invisible to operators.
Medium effort: containerize honcho + gateway too, with host networking for the gateway socket via a named bind-mount. You trade the XDG_RUNTIME_DIR mess for a docker-compose restart mess, but at least there's one control plane.
High effort: adopt a lightweight supervisor like s6-overlay or systemd inside a single "node" container. Overkill for the prototype, sensible if you ever ship a single-node appliance.
My recommendation is medium effort: move honcho + honcho-deriver into compose (they're already Postgres-backed), keep hermes-gateway host-native only because it has to spawn host-native hermes subprocesses that touch workspace directories on the host. The split then matches a real architectural boundary ("things that fork into host processes" vs. "things that don't") instead of an accidental one.

5. Retire network_mode: host for Paperclip
Phase E accepted host networking because Paperclip needs to reach the gateway UDS and the broker. But host mode kills compose DNS and forces every in-container config to use 127.0.0.1. A bridge-networked Paperclip with:

the gateway socket mounted from /run/user/$UID/hermes-gateway to /run/hermes-gateway (already done)
broker reachable via compose DNS as http://broker:8090
... would be strictly cleaner. The only reason host mode survived is that it was the fastest way to prove Phase E. This is a good candidate for a Phase E.5 cleanup commit.

6. Every generated artifact needs a make regenerate-X equivalent
The single biggest time-sink across all phases was editing a template and forgetting to re-render. .env, *.service, the profile tree, the skill tree. A future iteration should have a ./bin/1215 regenerate {env,units,profile,skills} surface, or — even better — a watcher that detects template changes and re-renders on the next up.

Execution-sequence recommendations
If I were re-running this plan from scratch, I'd reorder to minimize rework:

Phase 0 (new):  Substrate + broker schema + canary protocol
                (shared Postgres, shared MinIO, full broker DDL,
                 canary-planting pattern adopted)
Phase A:        Image pinning + node manifests + CI gate for digests
                (adds the digest-required lint that currently doesn't exist)
Phase B:        Honcho on shared Postgres
                (much smaller scope; no new DB to introduce)
Phase C:        hermes-gateway daemon (BEFORE profile setup)
                (the gateway is what enforces the profile allowlist;
                 having it first means the profile setup in D is
                 immediately exercised via the real spawn path)
Phase D:        orchestrator-ceo profile + skills
                (was C+F; combining them means the skills are
                 installed into a profile that can immediately
                 run them, not 3 phases later)
Phase E:        Paperclip container (bridge network from day one)
Phase F:        Langfuse instrumentation
                (unchanged — G today)
Phase G:        Unified launch script (unchanged — H today)
Phase H (new):  CI — codify the invariants
                (a small GitHub Action that runs ./bin/1215 smoke
                 on a throwaway VM; fails PRs on exposure / canary
                 / image-digest drift)
The net delta vs. the current plan:

Merges Phase C (profile) + Phase F (skills) — they have no real reason to be separate; skills live inside a profile. This would have saved an entire phase of "install profile, realize skills aren't there, install skills, re-test".
Swaps the order of C and D — the gateway enforces the profile contract, so building the enforcer first means the profile is validated by the real code path, not by a one-off hermes memory status invocation.
Adds Phase 0 (substrate/broker/canary as bedrock) and a new Phase H (CI gate). The former prevents 80% of the Phase B churn; the latter means invariants can't silently rot.
One thing the current plan got exactly right
Langfuse last. Putting observability after the runtime was working paid off enormously. Every other phase could assume "if the broker says it happened, it happened" without worrying about trace IDs. If Langfuse had been wired in early, the Phase G env-precedence bug (profile .env shadowing injected trace_id) would have surfaced as a silent data-quality issue across A–F instead of a contained bug fixed in one commit.

Happy to turn any of these into a docs/architecture/execution-plan-v2.md proposal if you want to try a second pass against a fork, or fold the recommendations into the existing roadmap.md. Just say the word.