#!/usr/bin/env bash
# Phase H unified launch script. Thin shim that delegates to `bin/1215 up`,
# which internally (a) seeds .env from init_env.py, (b) brings the substrate
# compose stack up with health waits, (c) enables the host-native systemd
# --user units for honcho / honcho-deriver / hermes-gateway, and (d) runs the
# smoke gate (exposure + canary + gate_shared_core).
#
# The goal is "fresh clone -> launch.sh -> everything healthy, no manual
# intervention required". Fail fast if any phase does not come up.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

cd "${REPO_ROOT}"

if [[ ! -x "${REPO_ROOT}/bin/1215" ]]; then
    echo "launch.sh: ${REPO_ROOT}/bin/1215 is missing or not executable" >&2
    exit 2
fi

exec "${REPO_ROOT}/bin/1215" up "$@"
