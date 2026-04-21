#!/usr/bin/env python3
"""Bootstrap the ``orchestrator-ceo`` Paperclip company.

Phase E deliverable. The paperclip service in
``stack/prototype-local/docker-compose.substrate.yml`` boots with an
empty database; this script idempotently creates the CEO-flavoured
company that the gateway/Hermes profile from Phases C+D targets.

Semantics:
  1. Wait for http://127.0.0.1:3100/api/health to return 200 (up to
     5 minutes; first boot runs a pglite migration). Fail loud with a
     clear pointer to ``docker compose logs paperclip`` on timeout.
  2. List existing companies via GET /api/companies. If one with
     ``name == "orchestrator-ceo"`` already exists, skip creation and
     return its id. This keeps re-runs free.
  3. Otherwise POST /api/companies with the Phase E canonical body.
  4. Prove the gateway path by running a one-off
     ``docker compose exec paperclip sh -c 'wget --spider $sock/healthz'``
     equivalent through the bind-mounted UDS, confirming the
     container can reach the host-native gateway.
  5. Emit a JSON summary on stdout for CI / parent scripts.

This script does NOT:
  - Start the Paperclip container (compose owns that).
  - Create agents or task graphs inside the company (that belongs to
    Phase F once the broadcast_* skills land).
  - Mutate any secret files.

Run with ``uv run python stack/prototype-local/scripts/bootstrap_paperclip_ceo.py``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from typing import Any
from urllib import error, request

PAPERCLIP_URL = "http://127.0.0.1:3100"
HEALTH_URL = f"{PAPERCLIP_URL}/api/health"
COMPANIES_URL = f"{PAPERCLIP_URL}/api/companies"
GATEWAY_SOCKET = "/run/hermes-gateway/gateway.sock"
COMPOSE_SERVICE = "paperclip"

CEO_COMPANY_BODY = {
    "name": "orchestrator-ceo",
    "description": (
        "Flagship Paperclip company routed through the host-native "
        "Hermes gateway (phase E/D/C wire-up). The CEO profile lives "
        "at /var/lib/hermes/orchestrator-ceo/.hermes/."
    ),
    "budgetMonthlyCents": 0,
}


def _get_json(url: str, *, timeout: float = 5.0) -> tuple[int, Any]:
    req = request.Request(url, method="GET", headers={"accept": "application/json"})
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, (json.loads(body) if body else None)
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8") if hasattr(exc, "read") else ""
        try:
            parsed = json.loads(body) if body else None
        except json.JSONDecodeError:
            parsed = body
        return exc.code, parsed


def _post_json(url: str, payload: dict[str, Any], *, timeout: float = 15.0) -> tuple[int, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        method="POST",
        data=data,
        headers={"content-type": "application/json", "accept": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, (json.loads(body) if body else None)
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8") if hasattr(exc, "read") else ""
        try:
            parsed = json.loads(body) if body else None
        except json.JSONDecodeError:
            parsed = body
        return exc.code, parsed


def wait_for_paperclip(timeout_seconds: int = 300) -> dict[str, Any]:
    """Block until /api/health returns 2xx. First boot runs migrations
    so the default 5-minute ceiling is intentional."""
    deadline = time.time() + timeout_seconds
    last_err: str | None = None
    while time.time() < deadline:
        try:
            status, body = _get_json(HEALTH_URL, timeout=3)
            if 200 <= status < 300:
                return body if isinstance(body, dict) else {"raw": body}
            last_err = f"HTTP {status}: {body!r}"
        except (error.URLError, ConnectionError, TimeoutError) as exc:
            last_err = str(exc)
        time.sleep(2)
    raise SystemExit(
        f"paperclip /api/health never became ready within {timeout_seconds}s; "
        f"last error: {last_err}\n"
        "Inspect with: docker compose -f stack/prototype-local/docker-compose.substrate.yml logs paperclip"
    )


def find_ceo_company() -> dict[str, Any] | None:
    status, body = _get_json(COMPANIES_URL)
    if status != 200:
        raise SystemExit(f"GET {COMPANIES_URL} returned {status}: {body!r}")
    # API may return either a bare list or {"items": [...]} — accept both
    if isinstance(body, dict) and "items" in body:
        companies = body["items"]
    elif isinstance(body, list):
        companies = body
    else:
        raise SystemExit(f"unexpected GET /api/companies shape: {body!r}")
    for company in companies:
        if isinstance(company, dict) and company.get("name") == CEO_COMPANY_BODY["name"]:
            return company
    return None


def create_ceo_company() -> dict[str, Any]:
    status, body = _post_json(COMPANIES_URL, CEO_COMPANY_BODY)
    if status != 201 or not isinstance(body, dict):
        raise SystemExit(
            f"POST {COMPANIES_URL} -> {status}: {body!r}\n"
            "In ``local_trusted`` mode this should always succeed over "
            "loopback; a 401/403 usually means PAPERCLIP_DEPLOYMENT_MODE "
            "slipped to ``authenticated``. Re-check the paperclip env "
            "inside the container with "
            "``docker compose -f stack/prototype-local/docker-compose.substrate.yml exec paperclip env | grep DEPLOYMENT``."
        )
    return body


def gateway_reachable_from_container() -> dict[str, Any]:
    """Run a one-shot curl inside the paperclip container against the
    bind-mounted gateway socket. Returns the parsed /healthz JSON.

    This is the Phase E "container -> gateway UDS -> host" end-to-end
    reachability proof; it intentionally does NOT start a run (that's
    an adapter-level test beyond Phase E scope)."""
    cmd = [
        "docker",
        "compose",
        "-f",
        "stack/prototype-local/docker-compose.substrate.yml",
        "exec",
        "-T",
        COMPOSE_SERVICE,
        "sh",
        "-c",
        f"command -v curl >/dev/null && curl -fsS --unix-socket {GATEWAY_SOCKET} http://localhost/healthz "
        f"|| wget -qO- --header='Host: localhost' --tries=1 {GATEWAY_SOCKET}/healthz 2>/dev/null "
        "|| (echo 'ERR: neither curl nor wget --unix-socket available in paperclip container'; exit 42)",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode == 42:
        return {
            "ok": None,
            "note": "container image lacks curl and wget --unix-socket; the bind-mount is present "
            "but cannot be exercised from inside the container without adding a client tool. "
            "Host-side curl --unix-socket still works and is exercised in Phase D acceptance.",
        }
    if result.returncode != 0:
        raise SystemExit(
            "gateway reachability probe from inside paperclip failed:\n"
            f"  rc={result.returncode}\n"
            f"  stdout={result.stdout[-400:]}\n"
            f"  stderr={result.stderr[-400:]}"
        )
    out = result.stdout.strip()
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"ok": True, "raw": out}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Seconds to wait for /api/health before giving up.",
    )
    parser.add_argument(
        "--skip-gateway-probe",
        action="store_true",
        help="Skip the docker compose exec gateway reachability probe.",
    )
    args = parser.parse_args()

    health = wait_for_paperclip(args.timeout)

    existing = find_ceo_company()
    if existing is not None:
        company = existing
        created = False
    else:
        company = create_ceo_company()
        created = True

    gateway_probe: dict[str, Any] | None = None
    if not args.skip_gateway_probe:
        gateway_probe = gateway_reachable_from_container()

    summary = {
        "paperclip_health": health,
        "company": {
            "id": company.get("id"),
            "name": company.get("name"),
            "status": company.get("status"),
            "created_this_run": created,
        },
        "gateway_probe": gateway_probe,
        "endpoints": {
            "paperclip_api": PAPERCLIP_URL,
            "gateway_socket_host": "/run/user/1000/hermes-gateway/gateway.sock",
            "gateway_socket_container": GATEWAY_SOCKET,
            "broker_in_network": "http://broker:8090",
        },
    }
    json.dump(summary, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
