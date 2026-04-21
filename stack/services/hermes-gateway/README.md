# hermes-gateway

Host-side daemon that brokers Hermes runs for the Paperclip container.

Paperclip-in-container never reaches Hermes-on-host directly. Instead, it
talks to this gateway over a bind-mounted UNIX domain socket; the gateway
enforces a profile allowlist, a workspace allowlist, a fixed `PATH`, and
per-profile secret files before spawning `hermes chat` as a host subprocess.
It publishes `run.created`, `run.started`, `run.completed`, and
`run.failed` to the broker at `http://127.0.0.1:8090` for continuity.

## Layout

```
hermes-gateway/
  hermes_gateway/        # Python package
    __init__.py
    spawn.py             # profile/workspace allowlists + Popen wrapper
    broker.py            # POST /events client (lifecycle publisher)
    app.py               # FastAPI app (phase_d.4)
  tests/                 # pytest, pytest-asyncio
  scripts/
    setup_ceo_profile.sh # one-off profile directory installer (phase C)
  pyproject.toml         # uv-managed
  hermes-gateway.service # systemd --user unit (phase_d.5)
  install.sh             # idempotent installer (phase_d.5)
```

## Socket path

The gateway binds `$XDG_RUNTIME_DIR/hermes-gateway/gateway.sock` (i.e.
`/run/user/$UID/hermes-gateway/gateway.sock`) instead of the roadmap's
suggested `/run/hermes-gateway/gateway.sock`. `/run/` is root-owned and
cannot hold a socket created by a `systemd --user` unit; the user runtime
directory is the correct parallel. Paperclip's compose entry bind-mounts
that exact host path into the container.

## Dev commands

```bash
# tests
uv run --project stack/services/hermes-gateway pytest

# manual run (foreground, for debugging)
uv run --project stack/services/hermes-gateway \
  uvicorn hermes_gateway.app:app --uds "$XDG_RUNTIME_DIR/hermes-gateway/gateway.sock"
```
