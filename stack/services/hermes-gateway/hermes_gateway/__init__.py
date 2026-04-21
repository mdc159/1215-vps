"""hermes-gateway — host-side UDS daemon that spawns Hermes runs.

Paperclip (in-container) talks to this gateway over a bind-mounted
UNIX domain socket at $XDG_RUNTIME_DIR/hermes-gateway/gateway.sock.
The gateway enforces the profile + workspace allowlists, reads
per-profile secrets from the host .env file at spawn time, and
publishes lifecycle events (run.created/started/completed/failed)
to the broker at http://127.0.0.1:8090.

Submodules:
    spawn   — allowlists + subprocess.Popen wrapper
    broker  — HTTP client for broker event publication
    app     — FastAPI app (built in phase_d.4)
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
