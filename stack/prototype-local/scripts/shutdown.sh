#!/usr/bin/env bash
# Phase H unified shutdown script. Thin shim that delegates to `bin/1215 down`,
# which stops the host systemd --user units first (hermes-gateway, honcho,
# honcho-deriver) and then brings the substrate compose stack down in reverse
# dependency order. Volumes are preserved by default — pass --volumes to nuke
# Postgres / MinIO / Langfuse state (destructive; confirm before running).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

cd "${REPO_ROOT}"

if [[ ! -x "${REPO_ROOT}/bin/1215" ]]; then
    echo "shutdown.sh: ${REPO_ROOT}/bin/1215 is missing or not executable" >&2
    exit 2
fi

exec "${REPO_ROOT}/bin/1215" down "$@"
