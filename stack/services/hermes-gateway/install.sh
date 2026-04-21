#!/usr/bin/env bash
#
# Install the hermes-gateway as a systemd --user unit.
#
# Idempotent. Steps:
#   1. uv sync --all-groups in this package so the .venv exists with
#      uvicorn[standard] available.
#   2. Render hermes-gateway.service.in with the absolute GATEWAY_DIR
#      and UVICORN_BIN paths for this checkout.
#   3. Install the rendered unit to $XDG_CONFIG_HOME/systemd/user/,
#      daemon-reload, and enable + start it.
#   4. Poll $XDG_RUNTIME_DIR/hermes-gateway/gateway.sock + /healthz
#      until the unit is healthy (up to ~20s).
#
# After this runs:
#   curl --unix-socket "$XDG_RUNTIME_DIR/hermes-gateway/gateway.sock" \
#        http://localhost/healthz
#   -> {"ok":true,"runs_in_flight":0}
#
# Pass --reinstall to force-replace the unit file even when the
# checksum matches. Pass --no-start to install without starting.

set -Eeuo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
gateway_dir="${script_dir}"
unit_template="${gateway_dir}/hermes-gateway.service.in"
unit_name="hermes-gateway.service"
systemd_user_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
runtime_dir="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
socket_path="${runtime_dir}/hermes-gateway/gateway.sock"

reinstall=0
start=1
for arg in "$@"; do
  case "${arg}" in
    --reinstall) reinstall=1 ;;
    --no-start) start=0 ;;
    -h|--help)
      sed -n '2,22p' "${BASH_SOURCE[0]}"
      exit 0
      ;;
    *) echo "ERROR: unknown argument '${arg}'." >&2; exit 2 ;;
  esac
done

if [[ ! -f "${unit_template}" ]]; then
  echo "ERROR: template missing: ${unit_template}" >&2
  exit 1
fi

command -v uv >/dev/null 2>&1 || {
  echo "ERROR: 'uv' not on PATH; install Astral uv first." >&2
  exit 1
}
command -v systemctl >/dev/null 2>&1 || {
  echo "ERROR: 'systemctl' not on PATH; this installer requires systemd." >&2
  exit 1
}

echo "[1/4] uv sync (all-groups) ..."
(cd "${gateway_dir}" && uv sync --all-groups --quiet)

uvicorn_bin="${gateway_dir}/.venv/bin/uvicorn"
if [[ ! -x "${uvicorn_bin}" ]]; then
  echo "ERROR: ${uvicorn_bin} not found or not executable after uv sync." >&2
  exit 1
fi

echo "[2/4] rendering unit ..."
rendered="$(mktemp)"
trap 'rm -f "${rendered}"' EXIT
sed -e "s|@GATEWAY_DIR@|${gateway_dir}|g" \
    -e "s|@UVICORN_BIN@|${uvicorn_bin}|g" \
    "${unit_template}" >"${rendered}"

mkdir -p "${systemd_user_dir}"
installed="${systemd_user_dir}/${unit_name}"
if [[ -f "${installed}" ]] && cmp -s "${rendered}" "${installed}" && [[ "${reinstall}" -eq 0 ]]; then
  echo "    unit unchanged: ${installed}"
else
  install -m 0644 "${rendered}" "${installed}"
  echo "    installed: ${installed}"
fi

echo "[3/4] systemctl --user daemon-reload ..."
systemctl --user daemon-reload

if [[ "${start}" -eq 0 ]]; then
  echo "Skipping start (per --no-start). To start: systemctl --user enable --now ${unit_name}"
  exit 0
fi

echo "[4/4] enabling + starting ${unit_name} ..."
systemctl --user enable "${unit_name}" >/dev/null
# `restart` is safe whether the unit was running or not.
systemctl --user restart "${unit_name}"

echo "    waiting for ${socket_path} ..."
deadline=$(( $(date +%s) + 20 ))
while (( $(date +%s) < deadline )); do
  if [[ -S "${socket_path}" ]]; then
    if curl -fsS --unix-socket "${socket_path}" http://localhost/healthz >/dev/null 2>&1; then
      echo "    /healthz OK"
      break
    fi
  fi
  sleep 0.5
done

if ! curl -fsS --unix-socket "${socket_path}" http://localhost/healthz >/dev/null 2>&1; then
  echo "ERROR: gateway did not become healthy. Logs:" >&2
  journalctl --user -u "${unit_name}" -n 40 --no-pager >&2 || true
  exit 1
fi

echo
echo "hermes-gateway is up."
echo "  socket : ${socket_path}"
echo "  status : systemctl --user status ${unit_name}"
echo "  logs   : journalctl --user -u ${unit_name} -f"
echo
echo "Smoke:"
echo "  curl --unix-socket ${socket_path} http://localhost/healthz"
echo "  curl --unix-socket ${socket_path} -X POST http://localhost/runs/start \\"
echo "       -H 'content-type: application/json' \\"
echo "       -d '{\"profile\":\"orchestrator-ceo\",\"session_id\":\"smoke-1\",\"prompt\":\"say hi in one word\"}'"
