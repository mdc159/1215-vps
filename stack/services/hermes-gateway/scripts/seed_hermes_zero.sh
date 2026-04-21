#!/usr/bin/env bash
#
# Seed the "hermes-zero" Hermes profile — the minimum-viable agent used
# to drive Tier 1 mechanical phase work (see
# docs/architecture/pitfalls-and-recoveries.md meta-lesson #6 and the
# two-tier bootstrap proposal in the chat retrospective).
#
# hermes-zero is deliberately isolated from orchestrator-ceo:
#   - its own profile dir at /var/lib/hermes/hermes-zero/
#   - its own workspace at /var/lib/paperclip/workspaces/hermes-zero/
#   - its own canary (HERMES_ZERO_CANARY)
#   - NO Honcho (memory.provider: none)
#   - NO broker dependency for skills to function
#   - NO Langfuse (observability optional — see --enable-langfuse)
#   - five stdlib-only seed skills: read_file, write_file, append_file,
#     run_shell, git_commit
#
# Design intent:
#   1. Hermes-zero can be brought up BEFORE any other 1215 service is
#      running (no substrate dependency). It needs only:
#        - a writable /var/lib/hermes/hermes-zero/ (created with sudo once)
#        - OPENROUTER_API_KEY (read from stack/prototype-local/.env if
#          present, or HERMES_ZERO_OPENROUTER_API_KEY env var as a
#          fallback for true "day zero" bootstrap).
#   2. Its skills are mechanical and verifier-friendly: every action
#      either succeeds with deterministic output or exits non-zero with
#      a grep-able error. This is the contract that makes Tier 1
#      supervisor-friendly.
#   3. Isolation from orchestrator-ceo is structural, not policy:
#      hermes-zero's workspace and profile are on different paths, so a
#      misconfigured hermes-zero can never accidentally write into the
#      CEO's Honcho memory or profile canary.
#
# Idempotent. Re-running preserves HERMES_ZERO_CANARY. Pass --force to
# regenerate .env / config.yaml / skill tree.
#
# Requires sudo only for the initial mkdir under /var/lib/hermes/.

set -Eeuo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../../../.." && pwd)"
env_source="${repo_root}/stack/prototype-local/.env"

profile_root="/var/lib/hermes/hermes-zero"
hermes_home="${profile_root}/.hermes"
workspace_root="/var/lib/paperclip/workspaces/hermes-zero"

force=0
enable_langfuse=0
for arg in "$@"; do
  case "${arg}" in
    --force) force=1 ;;
    --enable-langfuse) enable_langfuse=1 ;;
    -h|--help)
      sed -n '2,38p' "${BASH_SOURCE[0]}"
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument '${arg}'." >&2
      exit 2
      ;;
  esac
done

# -- OPENROUTER_API_KEY resolution --------------------------------------------
# Priority: env var > stack/prototype-local/.env > error. The env-var
# fallback is the "day zero" escape hatch — you haven't rendered the
# stack .env yet and you just want hermes-zero to do that for you.
openrouter_api_key="${HERMES_ZERO_OPENROUTER_API_KEY:-}"
langfuse_host=""
langfuse_public_key=""
langfuse_secret_key=""
if [[ -z "${openrouter_api_key}" ]] && [[ -f "${env_source}" ]]; then
  while IFS= read -r line; do
    [[ "${line}" =~ ^[[:space:]]*# ]] && continue
    [[ -z "${line//[[:space:]]/}" ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    case "${key}" in
      OPENROUTER_API_KEY) openrouter_api_key="${value}" ;;
      LANGFUSE_HOST) langfuse_host="${value}" ;;
      LANGFUSE_PUBLIC_KEY) langfuse_public_key="${value}" ;;
      LANGFUSE_SECRET_KEY) langfuse_secret_key="${value}" ;;
    esac
  done <"${env_source}"
fi

if [[ -z "${openrouter_api_key}" ]]; then
  cat >&2 <<'EOF'
ERROR: no OPENROUTER_API_KEY available. Provide one of:
  - export HERMES_ZERO_OPENROUTER_API_KEY=sk-or-v1-...
  - ensure OPENROUTER_API_KEY is set in stack/prototype-local/.env
    (run stack/prototype-local/scripts/init_env.py to render it).
EOF
  exit 1
fi

# -- Ensure host directories exist and are owned by the current user ---------
run_sudo() {
  if [[ "${EUID}" -eq 0 ]]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    echo "ERROR: need root (or sudo) to create ${profile_root} / ${workspace_root}." >&2
    exit 1
  fi
}

need_sudo=0
for p in "${profile_root}" "${workspace_root}"; do
  parent="$(dirname "${p}")"
  if [[ ! -d "${parent}" ]] || [[ ! -w "${parent}" ]]; then
    need_sudo=1
  fi
done

if [[ "${need_sudo}" -eq 1 ]]; then
  run_sudo mkdir -p "${hermes_home}/skills" \
                    "${hermes_home}/sessions" \
                    "${hermes_home}/logs" \
                    "${hermes_home}/memories" \
                    "${workspace_root}"
  run_sudo chown -R "${USER}:${USER}" "${profile_root}" "${workspace_root}"
else
  mkdir -p "${hermes_home}/skills" \
           "${hermes_home}/sessions" \
           "${hermes_home}/logs" \
           "${hermes_home}/memories" \
           "${workspace_root}"
fi

chmod 0750 "${profile_root}" "${workspace_root}" "${hermes_home}"

# -- Render ${hermes_home}/config.yaml (deliberately memoryless) --------------
config_path="${hermes_home}/config.yaml"
if [[ ! -f "${config_path}" ]] || [[ "${force}" -eq 1 ]]; then
  cat >"${config_path}" <<'YAML'
# Generated by stack/services/hermes-gateway/scripts/seed_hermes_zero.sh.
# Re-run with --force to regenerate.
#
# hermes-zero is intentionally MEMORYLESS. Every invocation starts from
# scratch with only the skill tree + the caller's prompt. This is the
# tier-0 seed; longer-horizon work belongs in orchestrator-ceo.
memory:
  provider: none
model: openai/gpt-4o-mini
YAML
fi

# -- Render ${hermes_home}/.env (OPENROUTER_API_KEY + canary) -----------------
env_path="${hermes_home}/.env"
existing_canary=""
if [[ -f "${env_path}" ]]; then
  existing_canary="$(grep -E '^HERMES_ZERO_CANARY=' "${env_path}" | head -n1 | cut -d= -f2- || true)"
fi
canary="${existing_canary:-FAKE_ZERO_SECRET_DO_NOT_LEAK_1215_Q9P3M7XN}"

langfuse_block=""
if [[ "${enable_langfuse}" -eq 1 ]] && [[ -n "${langfuse_host}" ]]; then
  langfuse_block="
# Langfuse observability (optional; --enable-langfuse was passed).
LANGFUSE_HOST=${langfuse_host}
LANGFUSE_PUBLIC_KEY=${langfuse_public_key}
LANGFUSE_SECRET_KEY=${langfuse_secret_key}"
fi

umask 077
cat >"${env_path}" <<EOF
# Generated by stack/services/hermes-gateway/scripts/seed_hermes_zero.sh.
# HOST-ONLY. Never commit. Re-rendering preserves HERMES_ZERO_CANARY.
#
# hermes-zero's canary is separate from orchestrator-ceo's: a leak here
# is scoped to the tier-0 seed and can be sandbox-isolated by rotating
# this file alone.
OPENROUTER_API_KEY=${openrouter_api_key}
HERMES_ZERO_CANARY=${canary}

# Workspace contract. Seed skills are hard-pinned to this directory;
# they refuse to operate on paths outside it. See skills/write_file.py.
HERMES_ZERO_WORKSPACE=${workspace_root}

# Broker URL is optional for hermes-zero. If set, the run-log skill
# will emit phase.started / phase.completed events for Tier-1 audit.
# If unset, skills fall back to local stdout/stderr logging.
BROKER_URL=http://127.0.0.1:8090
HERMES_NODE_ID=hermes-zero${langfuse_block}
EOF
chmod 0600 "${env_path}"

# -- Install seed skills ------------------------------------------------------
skills_source="${repo_root}/stack/services/hermes-gateway/skills/hermes-zero"
skills_dest="${hermes_home}/skills/hermes-zero"
if [[ -d "${skills_source}" ]]; then
  mkdir -p "${skills_dest}"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
      --exclude '__pycache__/' \
      --exclude '*.pyc' \
      "${skills_source}/" "${skills_dest}/"
  else
    rm -rf "${skills_dest}"
    mkdir -p "${skills_dest}"
    cp -R "${skills_source}/." "${skills_dest}/"
  fi
  find "${skills_dest}" -name '*.py' -not -name '_*.py' -print0 \
    | xargs -0 -r chmod 0755
fi

# -- Host-only README ---------------------------------------------------------
readme_path="${profile_root}/README.md"
cat >"${readme_path}" <<EOF
# hermes-zero Hermes profile (tier-0 seed)

Host-only directory. Do NOT commit.

Purpose: minimum-viable agent for driving mechanical phase work. Has
no long-term memory, no broker dependency for core skills, and is
isolated from orchestrator-ceo by path.

Layout:
  .hermes/
    config.yaml       # memory.provider: none
    .env              # OPENROUTER_API_KEY + HERMES_ZERO_CANARY (600)
    skills/
      hermes-zero/    # 5 seed skills — see SKILL.md files for contracts
    sessions/, logs/, memories/

Reproducible installer:
  stack/services/hermes-gateway/scripts/seed_hermes_zero.sh
  (pass --force to regenerate; --enable-langfuse to opt into tracing)

Companion workspace (all skills pin writes under this dir):
  ${workspace_root}

Invoke Hermes-zero:
  HERMES_HOME=${hermes_home} \\
    ${repo_root}/modules/hermes-agent/.venv/bin/hermes run \\
    "your Tier-1 task description here"

Canary (MUST NOT appear in any hermes-zero-produced artifact):
  ${canary}
EOF

# -- Summary ------------------------------------------------------------------
cat <<EOF
hermes-zero seed installed.

Paths:
  profile: ${profile_root}
  home:    ${hermes_home}
  env:     ${env_path}  (0600)
  skills:  ${skills_dest}/
  workspace: ${workspace_root}
  readme:  ${readme_path}

Quick smoke (does NOT require substrate / broker / honcho):
  HERMES_HOME=${hermes_home} \\
    ${repo_root}/modules/hermes-agent/.venv/bin/hermes --help

Canary (grep-check after any hermes-zero run):
  ${canary}
EOF
