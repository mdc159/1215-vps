# Pitfalls and Recoveries — Phases A through H

A retrospective log of the concrete traps I hit while executing
`docs/architecture/execution-plan.md` against this repo and the mitigations
that actually worked. Written after Phase H closed on branch `proto`.

This is **not** a rehash of the plan. It is a catalog of the non-obvious
failure modes that surfaced *between* the plan's bullet points — the
things future agents (or future me) will trip over again if they are not
written down.

Every entry is framed as **Pitfall → Symptom → Root cause → Fix →
Why this recurs**.

---

## Table of contents

1. [Cross-cutting traps](#cross-cutting-traps)
2. [Phase A — Tidy foundations](#phase-a--tidy-foundations)
3. [Phase B — Host-native Honcho](#phase-b--host-native-honcho)
4. [Phase C — Hermes `orchestrator-ceo` profile](#phase-c--hermes-orchestrator-ceo-profile)
5. [Phase D — hermes-gateway daemon](#phase-d--hermes-gateway-daemon)
6. [Phase E — Paperclip container](#phase-e--paperclip-container)
7. [Phase F — broadcast/artifact skills](#phase-f--broadcastartifact-skills)
8. [Phase G — Langfuse instrumentation](#phase-g--langfuse-instrumentation)
9. [Phase H — Unified launch](#phase-h--unified-launch)
10. [Meta-lessons](#meta-lessons)

---

## Cross-cutting traps

### 1. "System Python" vs "uv-managed venv Python" is a shifting target

**Symptom.** Scripts that worked when run by hand (`/usr/bin/python3
foo.py`) failed with `ModuleNotFoundError: No module named 'bcrypt'` the
moment the same script was invoked from a `uv run` context.

**Root cause.** Inside a `uv run --project stack/control ...` shell,
`sys.executable`, `shutil.which("python3")`, **and** `PATH`'s `python3` all
resolve to `stack/control/.venv/bin/python3`. That venv is deliberately
minimal (no bcrypt, no psycopg). The legacy prototype bootstrap scripts
(`bootstrap_n8n.py`, `sync_openwebui_functions.py`, …) were written
assuming host-Python deps.

**Fix.** For any subprocess that needs the host's site-packages, resolve
the interpreter explicitly:

```python
candidates = ["/usr/bin/python3", "python3"]
python = ""
for candidate in candidates:
    resolved = shutil.which(candidate) if not os.path.isabs(candidate) else (
        candidate if Path(candidate).exists() else None
    )
    if resolved:
        python = resolved
        break
if not python:
    python = sys.executable
```

**Why this recurs.** The user rule mandates `uv` for *this* project's
Python, but the prototype bootstrap tree predates that rule and relies on
system deps. Mixing the two will bite again whenever a gate script adds a
new top-level import.

---

### 2. "My changes don't take effect" — forgetting to re-render env / systemd units

**Symptom.** Edited `.env.example`, but containers still use the old
value. Edited `hermes-gateway.service.in`, but `systemctl --user status`
still shows the old `ExecStart`.

**Root cause.** The repo treats `.env` and `.service` as *generated*
artifacts:

- `stack/prototype-local/.env` is rendered from `.env.example` by
  `init_env.py` only when missing.
- `hermes-gateway.service` is rendered from `*.service.in` by
  `install.sh`, copied into `~/.config/systemd/user/`, and then cached
  by `systemctl --user daemon-reload`.

Editing the template without re-running the generator is a silent no-op.

**Fix.** After every change to a template, either delete the rendered
artifact and re-run, or run the installer script explicitly:

```bash
rm stack/prototype-local/.env             # force init_env.py to re-render
uv run stack/prototype-local/scripts/init_env.py

cd stack/services/hermes-gateway && ./install.sh
systemctl --user daemon-reload
systemctl --user restart hermes-gateway
```

**Why this recurs.** Two-layer templating (template → rendered file →
loaded-into-memory-by-daemon) is easy to forget, and the failure mode is
"code looks right but behaves wrong" — the worst kind.

---

### 3. Dropped tool calls / interrupted sessions losing run context

**Symptom.** In the middle of an integration acceptance, the conversation
was compacted or a tool call was interrupted. Re-reading the plan left
ambiguity about which sub-task was mid-flight.

**Fix.** The `TodoWrite` list is the single source of truth for
progress — not the chat transcript. Always mark a sub-task `in_progress`
before starting it and `completed` **immediately** after the closing
commit lands, not after the next sub-task begins. When restarting,
trust the todos, not memory.

**Why this recurs.** Summarization collapses context; todos survive
summarization because they are structured state.

---

## Phase A — Tidy foundations

### A.1 Image pins rot silently

**Symptom.** `docker compose up` pulled a different image sha than the
one committed last week, causing Langfuse → Clickhouse compatibility
drift.

**Root cause.** Several substrate images were pinned only by tag
(`langfuse/langfuse:3`, not `langfuse/langfuse:3@sha256:…`). Upstream
rebuilds under the same tag; Docker quietly re-pulls.

**Fix.** Every substrate image is pinned by `tag@sha256:` digest, with
the digest captured via `docker inspect` at commit time and recorded in
`docker-compose.substrate.yml`. When an image legitimately needs to
advance, it is bumped in a dedicated commit with the new digest and the
reason in the message.

**Why this recurs.** There is no CI gate that fails on a missing digest
yet. Adding one is Phase I territory.

### A.2 "Empty but version-controlled" overlay dirs are a trap

**Symptom.** The `stack/roles/builder/` overlay existed as an empty
directory with a `README.md` implying it was "coming soon". The loader
tried to include a non-existent compose file whenever the `builder` role
was enabled.

**Fix.** Either delete the overlay entirely or populate it with a real
`docker-compose.role.yml`. "Placeholder" subdirectories that are
referenced in the topology JSON must round-trip through the loader at
least once; otherwise they should not exist.

### A.3 Node manifest schema drift between `roles.env.example` and the loader

**Symptom (surfaced in Phase H).** `uv run pytest stack/control/tests/`
blew up with `ValueError: node 'linux-prototype' has no ENABLED_ROLES in
.../roles.env.example`.

**Root cause.** The manifest used `ROLES=core,media-cpu,tools` but
`control1215/nodes.py` expects `ENABLED_ROLES=`. A copy-paste from a
pre-rename era.

**Fix.** Renamed the key in the manifest. Added a CLI test
(`test_nodes_command_lists_manifest_examples`) that exercises the full
loader path, so the next drift fails fast.

**Why this recurs.** Env-var naming is invisible to the type system.
Only a test that actually parses the manifest catches this.

---

## Phase B — Host-native Honcho

### B.1 `pgvector` is not in stock `postgres:17`

**Symptom.** Honcho deriver crashed on startup with
`ERROR: extension "vector" does not exist`.

**Fix.** Swapped the substrate Postgres image to
`pgvector/pgvector:pg17` (digest-pinned) and extended
`postgres-bootstrap` to `CREATE DATABASE honcho` and `CREATE EXTENSION
IF NOT EXISTS vector` at startup. Bootstrap is idempotent, so existing
clusters upgrade cleanly on restart.

### B.2 Deriver service competes with itself

**Symptom.** Two `honcho-deriver` worker processes, occasional embedding
duplication.

**Root cause.** `systemd --user enable honcho-deriver.service` was run
twice (once by hand, once by the installer), and the previous manual
process was still alive.

**Fix.** The install script now does:

```bash
systemctl --user stop honcho-deriver.service 2>/dev/null || true
pkill -f honcho-deriver || true
systemctl --user daemon-reload
systemctl --user enable --now honcho-deriver.service
```

**Why this recurs.** `systemctl enable` does not adopt an already-running
process; it just ensures one will be started on next boot.

### B.3 Honcho's health path is `/health`, not `/v2/health`

**Symptom (surfaced in Phase H).** `./bin/1215 status` marked honcho
`unhealthy` even though the service was serving requests normally.

**Fix.** Read `http://127.0.0.1:18000/openapi.json` at runtime:

```
curl -s http://127.0.0.1:18000/openapi.json | python3 -c \
  "import sys,json; [print(p) for p in json.load(sys.stdin)['paths']]"
```

Updated the `ServiceSpec` entry to `healthz_url="…/health"`.

**Why this recurs.** Honcho's README and OpenAPI spec disagreed at the
time. Always trust the live OpenAPI.

### B.4 Old `1215-honcho-pg` container is still running

**Symptom.** Port 5432/18000 conflicts, deriver connects to the "wrong"
Postgres (the legacy one bundled into Honcho's old compose).

**Fix.** `setup_hermes_honcho_paperclip.py` retired the dedicated
`1215-honcho-pg` bring-up. Before enabling the new user units I had to
explicitly `docker rm -f 1215-honcho-pg` because the orphan container
was still bound to the same ports.

---

## Phase C — Hermes `orchestrator-ceo` profile

### C.1 `HERMES_HOME` is a subtle contract

**Symptom.** `hermes memory status` crashed with "no such profile" even
though the profile dir existed.

**Root cause.** Hermes resolves `HERMES_HOME` relative to the invoking
user's `$HOME` by default, but the setup script ran it as the *current*
shell user, whose `$HOME` was `/home/hammer`, not
`/var/lib/hermes/orchestrator-ceo`. The profile was installed at the
latter, and Hermes couldn't find it.

**Fix.** Every invocation of `hermes` from an automation script must
set `HERMES_HOME` explicitly:

```bash
HERMES_HOME=/var/lib/hermes/orchestrator-ceo/.hermes hermes memory status
```

The profile env file for `orchestrator-ceo` also sets `HERMES_HOME` so
that `systemctl --user` spawns inherit it.

### C.2 Canary leaks are easy to create with `cp -r`

**Symptom.** The test canary string (`CANARY-XYZ`) ended up in a
`skill_cache.json` inside the profile dir because the setup script
copied the *whole* onboarding template, including test fixtures.

**Fix.** The installer uses `rsync --exclude='**/test-*'
--exclude='**/canary*'` when materializing the skill tree. The Phase H
`canary_check` sweep is the backstop: it reads `/events`, `/artifacts`,
and Langfuse `/traces` looking for the canary, and fails the smoke gate
if it appears anywhere.

---

## Phase D — hermes-gateway daemon

### D.1 `XDG_RUNTIME_DIR` can be `None` under systemd

**Symptom.** `KeyError: 'XDG_RUNTIME_DIR'` at daemon startup when
launched by `systemctl --user` under certain session types.

**Fix.** Resolve the socket path with a fallback chain:

```python
runtime_dir = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
socket_path = Path(runtime_dir) / "hermes-gateway" / "gateway.sock"
```

Make sure the parent dir is created with `mode=0o700` before binding.

### D.2 Systemd stale sockets survive restart

**Symptom.** Restarting the gateway unit failed with `OSError: [Errno 98]
Address already in use`.

**Fix.** The FastAPI lifespan hook unlinks the socket on both startup
and shutdown:

```python
@asynccontextmanager
async def lifespan(app):
    socket_path.unlink(missing_ok=True)
    yield
    socket_path.unlink(missing_ok=True)
```

Combined with `Type=notify` in the systemd unit and a proper
`ExecStopPost=/bin/rm -f %t/hermes-gateway/gateway.sock`.

### D.3 422s from FastAPI are not self-documenting

**Symptom.** `POST /runs/start` returned 422 with a curt `curl: (22) The
requested URL returned error: 422`, no body visible.

**Fix.** Drop the `-f` flag on curl so the body comes through:

```bash
curl -sS ...     # prints {"detail":[{"loc":...,"msg":"Field required"}]}
```

Phase H integration test revealed `session_id` was required but missing
from the smoke invocation. Documented it in the README.

### D.4 Profile allowlist enforcement must be **before** any filesystem
      side-effect

**Symptom.** An early version created the run's workspace dir *then*
returned 403 for a bad profile, leaving orphan dirs.

**Fix.** The `build_spawn_plan` pure function validates profile +
workspace + env-file existence *before* any `mkdir`/`chmod` happens.
Unit tests pin this ordering with a mutation-style assertion.

---

## Phase E — Paperclip container

### E.1 `network_mode: host` disables Docker's DNS for the container

**Symptom.** Paperclip could not resolve `broker` as a hostname; it had
to use `127.0.0.1:8090` instead.

**Fix.** The Paperclip env in `.env`/compose now uses
`BROKER_URL=http://127.0.0.1:8090`. Host networking makes "service
discovery via compose network" impossible; the substitute is loopback
URLs that are valid precisely *because* the container shares the host
network namespace.

**Why this recurs.** Everyone who has only used `bridge` networks assumes
compose-name DNS "just works". In `host` mode it simply does not exist.

### E.2 UDS bind-mounts require that the *directory* exists at container
      start

**Symptom.** Paperclip started, but the gateway socket bind-mount was a
file-shaped empty placeholder because the gateway hadn't run yet.

**Fix.** Mount the *directory*, not the socket:

```yaml
volumes:
  - /run/user/1000/hermes-gateway:/run/hermes-gateway
```

And ensure `hermes-gateway.service` has `After=` and `Wants=` lines so it
starts before Paperclip. In the Phase H `./bin/1215 up` command, user
units are started *before* compose services that depend on them.

### E.3 The shipped Paperclip image has no `curl` / no `wget --unix-socket`

**Symptom.** `bootstrap_paperclip_ceo.py`'s in-container gateway probe
could not run, so the acceptance test had to fall back to a host-side
probe. This was worked-around rather than fixed.

**Decision.** Documented in the acceptance JSON output:

```json
"gateway_probe": {
  "ok": null,
  "note": "container image lacks curl and wget --unix-socket; the bind-mount is present but cannot be exercised from inside the container without adding a client tool."
}
```

Revisit when Paperclip adds a minimal HTTP client to its base image, or
add a sidecar with `curl` if that never happens.

---

## Phase F — broadcast/artifact skills

### F.1 Hand-rolled SigV4 is a nightmare the first time and easy after

**Symptom.** MinIO returned `403 SignatureDoesNotMatch` for a skill's
upload POST.

**Root cause.** Two bugs at once:
  - Canonical URI was URL-encoded twice (the library I borrowed from
    re-encoded `%2F` to `%252F`).
  - The `x-amz-content-sha256` header value didn't match the body because
    a newline was appended by the stdlib `urllib.request` body writer.

**Fix.** `stack/.../continuity-plane/_s3.py` now:
  - Uses `urllib.parse.quote(path, safe='/')` *exactly once*.
  - Computes the body sha256 on the *final* bytes after any encoding.
  - Has a unit test that diffs the canonical request string against a
    known-good fixture captured with `aws s3 cp --debug`.

### F.2 Replay cursors must be monotonic across restarts

**Symptom.** `broadcast_ack` re-delivered events after a restart because
the per-reader cursor was in-memory only.

**Fix.** Cursors are persisted in the broker as a `checkpoint` row
keyed by `(reader_id, topic)`. `broadcast_read_feed` is required to
commit a checkpoint before returning the batch. E2E acceptance now
kills and restarts the consumer mid-stream and asserts no duplicates.

### F.3 "Idempotent on `run_id`" is not free — it is an index

**Symptom.** The broker slowed down under load because every
`run.created` was doing a linear scan for duplicate `run_id`.

**Fix.** Added a `UNIQUE` index on `events(run_id, event_type)` where
`event_type IN ('run.created','run.started','run.completed','run.failed')`.
Broker test asserts the conflict path returns the existing row instead
of erroring.

---

## Phase G — Langfuse instrumentation

### G.1 Env-var precedence between injected IDs and profile `.env`

**Symptom.** Child Hermes spans showed an old `LANGFUSE_TRACE_ID` from a
stale profile `.env`, not the per-run id minted by the gateway.

**Root cause.** `spawn.py` originally did:

```python
env = {"HERMES_RUN_ID": run_id, "LANGFUSE_TRACE_ID": run_id, ...}
env.update(parse_env_file(env_file))   # ← profile overrides run id
```

Which is the opposite of what we want.

**Fix.** Inject run-scoped ids *after* the profile merge:

```python
env.update(parse_env_file(env_file))
env["HERMES_RUN_ID"] = run_id
env["LANGFUSE_TRACE_ID"] = run_id
env["LANGFUSE_SESSION_ID"] = session_id
```

The broker belt-and-suspenders this by auto-stamping
`metadata.langfuse_trace_id = run_id` on any event that carries a
`run_id`, so even a badly-configured child still correlates.

### G.2 Langfuse 3.x "self-hosted" does **not** auto-create projects

**Symptom.** Brand-new cluster: API returned 401 because no project
existed and no public key was valid.

**Fix.** Set `LANGFUSE_INIT_*` env vars in the compose file:

```yaml
LANGFUSE_INIT_ORG_ID: "prototype-local"
LANGFUSE_INIT_PROJECT_ID: "1215"
LANGFUSE_INIT_PROJECT_PUBLIC_KEY: ${LANGFUSE_PUBLIC_KEY}
LANGFUSE_INIT_PROJECT_SECRET_KEY: ${LANGFUSE_SECRET_KEY}
LANGFUSE_INIT_USER_EMAIL: ${LANGFUSE_INIT_USER_EMAIL}
LANGFUSE_INIT_USER_PASSWORD: ${LANGFUSE_INIT_USER_PASSWORD}
```

These run exactly once per empty DB. The prototype-local `.env.example`
ships consistent defaults so a fresh clone works without manual Langfuse
dashboard clicks.

### G.3 A failing Langfuse must never take the run down with it

**Symptom.** While testing, I tore down Langfuse mid-run. Every
subsequent run raised `httpx.ConnectError` from the gateway and failed.

**Fix.** The minimal Langfuse client swallows all network/HTTP errors
and logs a warning. Observability outages must not propagate into the
runtime. Unit test
`test_network_error_is_swallowed` pins this behaviour.

### G.4 Ingestion API expects *batches*, not single events

**Symptom.** Single `trace-create` POSTs returned 400.

**Fix.** The client always wraps events in the Langfuse 3.x batch
envelope:

```json
{"batch": [{"id": "...", "type": "trace-create", "timestamp": "...", "body": {...}}]}
```

Even for a single event.

---

## Phase H — Unified launch

### H.1 `docker ps` sees every container on the daemon, not just ours

**Symptom.** The exposure smoke gate reported *archon-ui*, *sisyphus*,
and several other unrelated containers as "leaking" on 0.0.0.0 — because
they were running under different compose projects on the same daemon.

**Fix.** Scope the docker query to the 1215 compose project:

```python
subprocess.run([
    "docker", "ps",
    "--filter", "label=com.docker.compose.project=1215-prototype-local",
    "--format", "{{.Names}}\t{{.Ports}}",
])
```

**Why this recurs.** Development machines accumulate compose projects.
Any invariant check that shells out to `docker ps` without a label
filter will have false positives within a month.

### H.2 Systemd unit-file discovery under `--user` is picky

**Symptom.** `systemctl --user is-active hermes-gateway` returned
`inactive` even though the daemon was clearly running.

**Root cause.** Unit name mismatch: the file on disk was
`hermes-gateway.service` but I'd queried `hermes-gateway` plus the unit
had been installed under `~/.local/share/systemd/user/` instead of
`~/.config/systemd/user/`. The former is for vendor-provided units; the
latter is for user-managed ones.

**Fix.** Installer writes to `~/.config/systemd/user/` exclusively.
Lifecycle code queries units by their exact file basename, including
the `.service` suffix.

### H.3 n8n-mcp rate-limits the bootstrap script across runs

**Symptom.** Running `./bin/1215 smoke` back-to-back failed the third
time with `(429) Too many authentication attempts`.

**Fix (operational).** `docker restart 1215-prototype-local-n8n-mcp-1`
resets the in-memory rate limiter. The smoke gate is explicitly *not*
idempotent in the sense of "safe to run every 10 seconds"; it is
designed to run once after bringup and occasionally for drift detection.

**Follow-up.** Consider `n8n-mcp` config to raise the auth-attempt
threshold, or add a `--light` flag to the gate that skips the n8n
bootstrap leg for frequent local re-runs.

### H.4 A pre-existing broken test is not "my" bug, but I still have to fix it

**Symptom.** `test_docs_command_lists_architecture_pack` failed because
it asserted on the filename `inter-node-data-flow.md`, which had been
renamed to `execution-plan.md` several phases earlier.

**Fix.** Updated the assertion. Resisted the urge to `git blame` — a
failing test blocks the phase-closing commit, regardless of who wrote it.

**Why this recurs.** A long-running plan will always surface test-rot
that was already latent. Budget time for it in every phase-close.

### H.5 Test monkey-patches that read the wrong `argv` index

**Symptom.** `test_canary_check_flags_broker_leak` passed `assert not
ok`, i.e. it expected a leak but the test returned clean.

**Root cause.** The test's fake_run inspected `argv[3]` to decide which
fixture payload to return, but `argv` was
`["curl", "-fsS", "-m", "3", url]`, so `argv[3]` was `"3"` — the timeout
flag value, not the URL.

**Fix.** `argv[-1]` is the URL:

```python
def fake_run(argv, **kwargs):
    url = argv[-1] if argv else ""
    payload = (
        '{"events": [{"payload_json": "CANARY-XYZ"}]}'
        if "events" in url else "{}"
    )
```

**Why this recurs.** Index-based `argv` inspection is fragile whenever
the command flags change. Prefer substring-against-joined-argv, or
better, parse the curl call once.

---

## Meta-lessons

### 1. "Acceptance" must run in the same shell the operator will use

Every "my machine works" pitfall in this log boils down to this. When
the plan says *"run the smoke gate"*, it means: exactly the same entry
point, exactly the same env, exactly the same order of steps a fresh
clone would follow. That's why `./bin/1215 up && ./bin/1215 smoke` is
the acceptance invocation for Phase H — not a clever one-off I ran
inline.

### 2. The broker is the truth; everything else is cache

Whenever I doubted whether an event *really* happened — was the run
actually started? Did the artifact actually upload? Did Langfuse get
the trace? — querying the broker was always faster and more reliable
than reading a log file or the Langfuse UI. Every phase ended with me
piping `curl /events?run_id=…` through `jq`/`python -m json.tool`.

### 3. Idempotency is a *testable* property, not a *hope*

Every bringup script, every skill, every broker POST should be safe to
run twice in a row. Where I cut corners on this (Phase B's
`postgres-bootstrap`, Phase F's replay cursor) I paid for it in the
next phase's acceptance. Unit tests of the form "call the thing twice,
assert same result" caught more regressions than any other pattern.

### 4. Observability must not be on the critical path

The Langfuse outage drill in Phase G was an unplanned gift. It forced
the gateway's Langfuse client to be strictly fire-and-forget, which in
turn made the broker's auto-stamping of `metadata.langfuse_trace_id`
the real correlation backbone — the broker is always up when a run
is up; Langfuse may not be.

### 5. Generated artifacts need a re-render command, documented

`.env`, `*.service`, installed skill trees, the profile dir — all are
generated. Every one of them should have a documented "re-render this"
one-liner in `stack/prototype-local/README.md`. The two-layer silent
no-op (*"I edited the template, why didn't anything change?"*) was the
single largest time-sink of the plan.

### 6. Claim-first, verify-always

When I claimed a phase was complete, I was sometimes wrong — Phase H
alone surfaced four latent bugs left from A, B, and earlier test drift.
The verification-before-completion skill is not optional; every phase
close has to re-run the acceptance locally, not trust the last green
run from yesterday.

---

## See also

- [`docs/architecture/execution-plan.md`](/mnt/data/Documents/repos/1215-vps/docs/architecture/execution-plan.md) — the phased plan this retrospective follows.
- [`docs/architecture/north-star.md`](/mnt/data/Documents/repos/1215-vps/docs/architecture/north-star.md) — the invariants (local-only, loopback-bound, canary-free) that Phase H's smoke gate enforces programmatically.
- [`stack/prototype-local/README.md`](/mnt/data/Documents/repos/1215-vps/stack/prototype-local/README.md) — the operator-facing entry for `./bin/1215 {up,down,status,logs,smoke}`.
- [`stack/control/control1215/lifecycle.py`](/mnt/data/Documents/repos/1215-vps/stack/control/control1215/lifecycle.py) — the service registry and smoke checks referenced throughout Phase H.
