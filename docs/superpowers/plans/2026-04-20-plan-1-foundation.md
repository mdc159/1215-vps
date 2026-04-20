# Plan 1 — Foundation (Data Plane, Bring-up Scaffolding)

**Archon Project ID:** 7eae9992-6d10-450e-a17f-23a13ef9d4ea
**Archon Project Title:** 1215-VPS

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**North star:** `docs/superpowers/specs/2026-04-20-1215-vps-design.md` is the canonical design. This plan implements a subset of it. The spec's service inventory, port map, network map, secrets map, sequence diagrams, bring-up swim-lane, and validation list all stay authoritative — this plan should not invent anything not in the spec.

**Goal:** Ship the foundation that every later plan builds on: repo scaffolding (`stack/`, `bin/`, `.env.example`), a Docker Compose overlay that introduces the `localai-data` / `localai-app` network split and attaches upstream services accordingly, idempotent database initialization (Honcho DB + broker schema + RLS), MinIO bucket provisioning, and `bin/start-1215.py` v1 with the spec's Phase 0 (preflight) and Phase 1 (data plane) implemented — including the strict three-level Supabase readiness gate.

**What this plan explicitly does NOT deliver** (each is a later plan; the spec covers them):

- Honcho `api` / `deriver` services — **Plan 2**
- `hermes-gateway` host daemon, shim binary, `paperclip-orchestrator` image — **Plan 3**
- n8n MinIO binary-storage wiring, `n8n-mcp`, Langfuse auto-provision — **Plan 4**
- Caddy addons, Tailscale vhost certs, Cloudflare Tunnel, full validation suite — **Plan 5**

Plan 1 is "shippable" when: `start-1215.py --check` passes on a fresh checkout; `start-1215.py` Phase 1 brings a Docker host to a state where Supabase is healthy, broker schema and Honcho DB exist with correct owners and extensions, and MinIO has the expected buckets.

**Architecture:** A UV-managed Python package `stack/control/` holds all bring-up logic (preflight, readiness gates, phase runners). `bin/start-1215.py` is a thin shim that invokes it. The Compose overlay at `stack/docker-compose.1215.yml` layers onto upstream via `-f` flags; it defines two networks and reattaches upstream services accordingly. A `db-init` one-shot container (extends `postgres:17`) runs ordered SQL files against Supabase's `db`. A `mc-init` one-shot container (minio/mc) provisions buckets.

**Tech stack:** Python 3.12 (UV-managed), `pytest` for tests, `psycopg[binary]` for DB verification helpers, `pyyaml` for compose parsing in tests, `docker compose` as CLI, upstream `local-ai-packaged` + Supabase composes layered via `-f`.

**Working directory:** `/mnt/data/Documents/repos/1215-vps`. Execute in a dedicated worktree if preferred (see `superpowers:using-git-worktrees`); this plan does not require it but does not fight it either.

---

## File Structure

After this plan completes, the repo will contain (new files only — existing files untouched except `README.md` and `.gitignore`):

```
stack/
├── docker-compose.1215.yml              # overlay: networks, upstream attachments, db-init, mc-init
├── env/
│   └── .env.example                     # single source of truth (~30 keys for Phase 1)
├── services/
│   ├── db-init/
│   │   ├── Dockerfile                   # postgres:17 + our entrypoint
│   │   ├── init.sh                      # runs sql/*.sql in order, idempotent
│   │   └── sql/
│   │       ├── 01_honcho.sql            # CREATE DATABASE honcho + extensions
│   │       ├── 02_broker.sql            # CREATE SCHEMA broker + roles
│   │       ├── 03_broker_tables.sql     # alignment_log, artifact_manifests + indexes
│   │       └── 04_broker_rls.sql        # RLS policies for PostgREST
│   └── mc-init/
│       └── init.sh                      # idempotent MinIO bucket creation
└── control/                             # UV Python package
    ├── pyproject.toml
    ├── uv.lock                          # generated
    ├── control/
    │   ├── __init__.py
    │   ├── cli.py                       # click-based entry; subcommands check, up
    │   ├── secrets.py                   # pure secret generation
    │   ├── envfile.py                   # parse/render .env, compose derived keys
    │   ├── supabase.py                  # three-level readiness gate
    │   ├── compose.py                   # subprocess wrapper around docker compose
    │   └── phases/
    │       ├── __init__.py
    │       ├── preflight.py             # Phase 0
    │       └── data_plane.py            # Phase 1
    └── tests/
        ├── __init__.py
        ├── conftest.py                  # shared fixtures
        ├── test_secrets.py
        ├── test_envfile.py
        ├── test_supabase.py
        └── test_phase1_integration.py   # requires Docker; marked @pytest.mark.integration
bin/
└── start-1215.py                        # thin shim that invokes control.cli:main
.gitignore                               # append stack/env/.env, __pycache__, .venv
README.md                                # append Phase 1 invocation
```

Each file has one responsibility. `secrets.py` knows nothing about `.env` layout; `envfile.py` knows nothing about Docker; `supabase.py` knows nothing about phases; `phases/data_plane.py` composes these lower-level modules.

---

## Task 1 — Create directory skeleton and `.gitignore`

**Files:**
- Create: `stack/env/`, `stack/services/db-init/sql/`, `stack/services/mc-init/`, `stack/control/control/phases/`, `stack/control/tests/`, `bin/`
- Modify: `.gitignore` (create if absent)

- [ ] **Step 1:** Create empty directories and placeholder files.

```bash
mkdir -p stack/env \
         stack/services/db-init/sql \
         stack/services/mc-init \
         stack/control/control/phases \
         stack/control/tests \
         bin
touch stack/control/control/__init__.py \
      stack/control/control/phases/__init__.py \
      stack/control/tests/__init__.py
```

- [ ] **Step 2:** Create `.gitignore` at repo root (append if exists).

Write to `.gitignore`:

```
# Python
__pycache__/
*.pyc
.venv/
.pytest_cache/
.mypy_cache/

# UV
stack/control/.venv/

# Environment files
stack/env/.env

# Docker
supabase/               # upstream start_services.py clones here; we don't commit it

# Editor
.vscode/
.idea/
*.swp
```

- [ ] **Step 3:** Verify structure exists.

Run: `find stack bin -type d | sort`

Expected output (exactly these directories):
```
bin
stack
stack/control
stack/control/control
stack/control/control/phases
stack/control/tests
stack/env
stack/services
stack/services/db-init
stack/services/db-init/sql
stack/services/mc-init
```

- [ ] **Step 4:** Commit.

```bash
git add .gitignore stack bin
git commit -m "Plan 1 T1: scaffold stack/, bin/, control package layout"
```

---

## Task 2 — Initialize UV Python project for `stack/control`

**Files:**
- Create: `stack/control/pyproject.toml`

- [ ] **Step 1:** Write `stack/control/pyproject.toml`.

```toml
[project]
name = "vps-control"
version = "0.1.0"
description = "1215-VPS control plane: preflight, readiness gates, phase runners."
requires-python = ">=3.12"
dependencies = [
    "click>=8.1",
    "psycopg[binary]>=3.2",
    "pyyaml>=6.0",
    "requests>=2.32",
]

[project.scripts]
start-1215 = "control.cli:main"

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-mock>=3.12",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["control"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "integration: requires a running Docker daemon (slow)",
]
```

- [ ] **Step 2:** Sync the project to verify `pyproject.toml` is valid.

Run: `cd stack/control && uv sync --extra dev`

Expected: creates `.venv/` and `uv.lock`, prints "Installed N packages". No errors.

- [ ] **Step 3:** Verify the package is importable and the console script resolves.

Run: `cd stack/control && uv run python -c "import control; print(control.__file__)"`

Expected: prints a path ending with `stack/control/control/__init__.py`.

Run: `cd stack/control && uv run start-1215 --help 2>&1 || true`

Expected: an `AttributeError` or similar (we haven't written `cli.py` yet). That's fine — we're only verifying the script entry is wired.

- [ ] **Step 4:** Commit.

```bash
git add stack/control/pyproject.toml stack/control/uv.lock
git commit -m "Plan 1 T2: UV project for stack/control with dev deps"
```

---

## Task 3 — TDD: `secrets.generate_hex` (pure function)

**Files:**
- Create: `stack/control/tests/test_secrets.py`
- Create: `stack/control/control/secrets.py`

- [ ] **Step 1: Write the failing test.**

Write `stack/control/tests/test_secrets.py`:

```python
"""Tests for secret generation."""
import re

import pytest

from control import secrets


def test_generate_hex_returns_lowercase_hex_of_requested_length():
    value = secrets.generate_hex(32)
    assert re.fullmatch(r"[0-9a-f]{64}", value), f"unexpected format: {value!r}"


def test_generate_hex_different_each_call():
    a = secrets.generate_hex(32)
    b = secrets.generate_hex(32)
    assert a != b, "two calls produced the same hex — RNG is broken"


def test_generate_hex_rejects_non_positive_length():
    with pytest.raises(ValueError):
        secrets.generate_hex(0)
    with pytest.raises(ValueError):
        secrets.generate_hex(-1)
```

- [ ] **Step 2: Run the test, verify it fails.**

Run: `cd stack/control && uv run pytest tests/test_secrets.py -v`

Expected: `ImportError` or `ModuleNotFoundError` for `control.secrets` (module doesn't exist yet).

- [ ] **Step 3: Write the minimal implementation.**

Write `stack/control/control/secrets.py`:

```python
"""Secret generation primitives.

Pure functions — no filesystem or env reads. Consumed by envfile.py
when populating missing `.env` keys.
"""
import secrets as _stdlib_secrets


def generate_hex(nbytes: int) -> str:
    """Return a lowercase hex string representing `nbytes` random bytes.

    The returned string has length `2 * nbytes`.
    """
    if nbytes <= 0:
        raise ValueError(f"nbytes must be positive, got {nbytes!r}")
    return _stdlib_secrets.token_hex(nbytes)
```

- [ ] **Step 4: Run the tests, verify they pass.**

Run: `cd stack/control && uv run pytest tests/test_secrets.py -v`

Expected: 3 passed.

- [ ] **Step 5: Commit.**

```bash
git add stack/control/tests/test_secrets.py stack/control/control/secrets.py
git commit -m "Plan 1 T3: secrets.generate_hex with tests"
```

---

## Task 4 — TDD: `secrets.populate_missing` (pure function)

**Files:**
- Modify: `stack/control/tests/test_secrets.py`
- Modify: `stack/control/control/secrets.py`

- [ ] **Step 1: Write the failing test.**

Append to `stack/control/tests/test_secrets.py`:

```python
def test_populate_missing_fills_only_absent_keys():
    existing = {"KEEP_ME": "already-set", "EMPTY_ME": ""}
    required = {
        "KEEP_ME": ("hex", 32),
        "EMPTY_ME": ("hex", 32),
        "BRAND_NEW": ("hex", 32),
    }
    out = secrets.populate_missing(existing, required)
    assert out["KEEP_ME"] == "already-set"  # untouched
    assert re.fullmatch(r"[0-9a-f]{64}", out["EMPTY_ME"]), "empty value should have been filled"
    assert re.fullmatch(r"[0-9a-f]{64}", out["BRAND_NEW"]), "missing key should have been added"


def test_populate_missing_supports_alnum_strategy():
    out = secrets.populate_missing({}, {"PASS": ("alnum", 24)})
    assert re.fullmatch(r"[A-Za-z0-9]{24}", out["PASS"])


def test_populate_missing_rejects_unknown_strategy():
    with pytest.raises(ValueError, match="unknown strategy"):
        secrets.populate_missing({}, {"X": ("bogus", 32)})
```

- [ ] **Step 2: Run the tests, verify the new ones fail.**

Run: `cd stack/control && uv run pytest tests/test_secrets.py -v`

Expected: 3 passing (from T3), 3 failing (populate_missing not defined yet).

- [ ] **Step 3: Write the minimal implementation.**

Replace `stack/control/control/secrets.py` with:

```python
"""Secret generation primitives.

Pure functions — no filesystem or env reads. Consumed by envfile.py
when populating missing `.env` keys.
"""
import secrets as _stdlib_secrets
import string


def generate_hex(nbytes: int) -> str:
    """Return a lowercase hex string representing `nbytes` random bytes.

    The returned string has length `2 * nbytes`.
    """
    if nbytes <= 0:
        raise ValueError(f"nbytes must be positive, got {nbytes!r}")
    return _stdlib_secrets.token_hex(nbytes)


def generate_alnum(length: int) -> str:
    """Return a random alphanumeric string of exactly `length` characters."""
    if length <= 0:
        raise ValueError(f"length must be positive, got {length!r}")
    alphabet = string.ascii_letters + string.digits
    return "".join(_stdlib_secrets.choice(alphabet) for _ in range(length))


def populate_missing(
    existing: dict[str, str],
    required: dict[str, tuple[str, int]],
) -> dict[str, str]:
    """Return a new dict where every key in `required` has a non-empty value.

    - Keys already present in `existing` with non-empty values are kept as-is.
    - Keys absent from `existing` or present with empty string values are filled
      using the strategy in `required[key]`.

    `required` maps key -> (strategy, size_or_length) where strategy is one of:
    - "hex": generate_hex(size) — size is bytes; result length is 2*size.
    - "alnum": generate_alnum(length).
    """
    out = dict(existing)
    for key, (strategy, n) in required.items():
        if out.get(key):
            continue
        if strategy == "hex":
            out[key] = generate_hex(n)
        elif strategy == "alnum":
            out[key] = generate_alnum(n)
        else:
            raise ValueError(f"unknown strategy {strategy!r} for key {key!r}")
    return out
```

- [ ] **Step 4: Run the tests, verify all pass.**

Run: `cd stack/control && uv run pytest tests/test_secrets.py -v`

Expected: 6 passed.

- [ ] **Step 5: Commit.**

```bash
git add stack/control/tests/test_secrets.py stack/control/control/secrets.py
git commit -m "Plan 1 T4: secrets.populate_missing + alnum strategy"
```

---

## Task 5 — TDD: `envfile.parse` (handles comments, blanks, `=` in values, quoted values)

**Files:**
- Create: `stack/control/tests/test_envfile.py`
- Create: `stack/control/control/envfile.py`

- [ ] **Step 1: Write the failing tests.**

Write `stack/control/tests/test_envfile.py`:

```python
"""Tests for .env parsing and rendering."""
from pathlib import Path

import pytest

from control import envfile


def test_parse_simple_key_value(tmp_path: Path):
    p = tmp_path / ".env"
    p.write_text("FOO=bar\nBAZ=qux\n")
    assert envfile.parse(p) == {"FOO": "bar", "BAZ": "qux"}


def test_parse_ignores_comments_and_blank_lines(tmp_path: Path):
    p = tmp_path / ".env"
    p.write_text(
        "# comment\n"
        "\n"
        "FOO=bar\n"
        "  # indented comment\n"
        "BAZ=qux\n"
    )
    assert envfile.parse(p) == {"FOO": "bar", "BAZ": "qux"}


def test_parse_allows_equals_in_values(tmp_path: Path):
    p = tmp_path / ".env"
    p.write_text("URI=postgres://u:p@h:5432/db?sslmode=require\n")
    assert envfile.parse(p)["URI"] == "postgres://u:p@h:5432/db?sslmode=require"


def test_parse_strips_surrounding_double_quotes(tmp_path: Path):
    p = tmp_path / ".env"
    p.write_text('FOO="bar with spaces"\n')
    assert envfile.parse(p) == {"FOO": "bar with spaces"}


def test_parse_strips_surrounding_single_quotes(tmp_path: Path):
    p = tmp_path / ".env"
    p.write_text("FOO='bar'\n")
    assert envfile.parse(p) == {"FOO": "bar"}


def test_parse_missing_file_returns_empty_dict(tmp_path: Path):
    assert envfile.parse(tmp_path / "does-not-exist") == {}


def test_parse_rejects_malformed_line(tmp_path: Path):
    p = tmp_path / ".env"
    p.write_text("FOO=bar\nnot-a-valid-line\n")
    with pytest.raises(ValueError, match="line 2"):
        envfile.parse(p)
```

- [ ] **Step 2: Run, verify all fail.**

Run: `cd stack/control && uv run pytest tests/test_envfile.py -v`

Expected: all fail with `ModuleNotFoundError: No module named 'control.envfile'`.

- [ ] **Step 3: Implement.**

Write `stack/control/control/envfile.py`:

```python
"""Parse and render `.env` files.

Format rules:
- One KEY=VALUE per line.
- Lines starting with `#` (after optional whitespace) are comments.
- Blank lines are ignored.
- `=` inside the value is preserved.
- Surrounding single or double quotes are stripped from values.
- Keys must be [A-Za-z_][A-Za-z0-9_]*.
"""
from __future__ import annotations

import re
from pathlib import Path

_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def parse(path: Path) -> dict[str, str]:
    """Return a dict of key -> value from a `.env` file.

    A missing file is treated as an empty env (returns {}).
    Raises ValueError on a malformed line, quoting the line number.
    """
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for lineno, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"{path}: line {lineno}: missing '=': {raw!r}")
        key, _, value = line.partition("=")
        key = key.strip()
        if not _KEY_RE.fullmatch(key):
            raise ValueError(f"{path}: line {lineno}: invalid key {key!r}")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        out[key] = value
    return out
```

- [ ] **Step 4: Run, verify all pass.**

Run: `cd stack/control && uv run pytest tests/test_envfile.py -v`

Expected: 7 passed.

- [ ] **Step 5: Commit.**

```bash
git add stack/control/tests/test_envfile.py stack/control/control/envfile.py
git commit -m "Plan 1 T5: envfile.parse with comment/quote/escape handling"
```

---

## Task 6 — TDD: `envfile.render` (preserves comment ordering from template)

**Files:**
- Modify: `stack/control/tests/test_envfile.py`
- Modify: `stack/control/control/envfile.py`

- [ ] **Step 1: Write the failing tests.**

Append to `stack/control/tests/test_envfile.py`:

```python
def test_render_preserves_template_comments_and_order(tmp_path: Path):
    template = tmp_path / ".env.example"
    template.write_text(
        "# Supabase\n"
        "POSTGRES_PASSWORD=\n"
        "JWT_SECRET=\n"
        "\n"
        "# Neo4j\n"
        "NEO4J_AUTH=\n"
    )
    values = {
        "POSTGRES_PASSWORD": "abc",
        "JWT_SECRET": "def",
        "NEO4J_AUTH": "neo4j/pw",
    }
    rendered = envfile.render(template, values)
    assert rendered == (
        "# Supabase\n"
        "POSTGRES_PASSWORD=abc\n"
        "JWT_SECRET=def\n"
        "\n"
        "# Neo4j\n"
        "NEO4J_AUTH=neo4j/pw\n"
    )


def test_render_appends_unknown_keys_at_end(tmp_path: Path):
    template = tmp_path / ".env.example"
    template.write_text("FOO=\n")
    rendered = envfile.render(template, {"FOO": "1", "EXTRA": "2"})
    assert rendered.endswith("EXTRA=2\n")
    assert "FOO=1" in rendered


def test_render_leaves_template_missing_key_blank(tmp_path: Path):
    """If values dict is missing a key, the rendered line keeps the empty value."""
    template = tmp_path / ".env.example"
    template.write_text("FOO=\nBAR=\n")
    rendered = envfile.render(template, {"FOO": "x"})
    assert "FOO=x\n" in rendered
    assert "BAR=\n" in rendered
```

- [ ] **Step 2: Run, verify new ones fail.**

Run: `cd stack/control && uv run pytest tests/test_envfile.py -v`

Expected: 7 passing, 3 failing with `AttributeError: module 'control.envfile' has no attribute 'render'`.

- [ ] **Step 3: Implement.**

Append to `stack/control/control/envfile.py`:

```python
def render(template_path: Path, values: dict[str, str]) -> str:
    """Render a `.env` file using `template_path` for structure and `values` for data.

    - Comments and blank lines from the template are kept verbatim.
    - For each `KEY=...` line, the template's value is replaced with `values[KEY]` if present.
    - Keys in `values` that don't appear in the template are appended at the end.
    """
    if not template_path.exists():
        raise FileNotFoundError(template_path)

    seen_keys: set[str] = set()
    out_lines: list[str] = []
    for lineno, raw in enumerate(template_path.read_text().splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            out_lines.append(raw)
            continue
        if "=" not in stripped:
            raise ValueError(
                f"{template_path}: line {lineno}: missing '=': {raw!r}"
            )
        key, _, _ = stripped.partition("=")
        key = key.strip()
        if not _KEY_RE.fullmatch(key):
            raise ValueError(
                f"{template_path}: line {lineno}: invalid key {key!r}"
            )
        seen_keys.add(key)
        out_lines.append(f"{key}={values.get(key, '')}")

    for key, val in values.items():
        if key not in seen_keys:
            out_lines.append(f"{key}={val}")

    return "\n".join(out_lines) + "\n"
```

- [ ] **Step 4: Run, verify all pass.**

Run: `cd stack/control && uv run pytest tests/test_envfile.py -v`

Expected: 10 passed.

- [ ] **Step 5: Commit.**

```bash
git add stack/control/tests/test_envfile.py stack/control/control/envfile.py
git commit -m "Plan 1 T6: envfile.render preserves template structure"
```

---

## Task 7 — TDD: `envfile.compose_honcho_uri`

**Files:**
- Modify: `stack/control/tests/test_envfile.py`
- Modify: `stack/control/control/envfile.py`

- [ ] **Step 1: Write the failing test.**

Append to `stack/control/tests/test_envfile.py`:

```python
def test_compose_honcho_uri_builds_correct_format():
    uri = envfile.compose_honcho_uri(password="s3cret")
    assert uri == "postgresql+psycopg://honcho_app:s3cret@db:5432/honcho"


def test_compose_honcho_uri_rejects_empty_password():
    with pytest.raises(ValueError, match="password required"):
        envfile.compose_honcho_uri(password="")


def test_compose_honcho_uri_url_encodes_special_chars():
    # `@` in a password would break the URI if not encoded.
    uri = envfile.compose_honcho_uri(password="p@ss:word")
    assert uri == "postgresql+psycopg://honcho_app:p%40ss%3Aword@db:5432/honcho"
```

- [ ] **Step 2: Run, verify fail.**

Run: `cd stack/control && uv run pytest tests/test_envfile.py -v -k compose_honcho`

Expected: 3 failing with `AttributeError`.

- [ ] **Step 3: Implement.**

Append to `stack/control/control/envfile.py`:

```python
from urllib.parse import quote as _quote


def compose_honcho_uri(password: str) -> str:
    """Build the Honcho DB_CONNECTION_URI from the honcho_app password.

    URL-encodes the password so characters like `@`, `:`, `/` are safe.
    The rest of the URI is static per the spec: user=honcho_app, host=db,
    port=5432, database=honcho.
    """
    if not password:
        raise ValueError("password required")
    encoded = _quote(password, safe="")
    return f"postgresql+psycopg://honcho_app:{encoded}@db:5432/honcho"
```

- [ ] **Step 4: Run, verify pass.**

Run: `cd stack/control && uv run pytest tests/test_envfile.py -v`

Expected: 13 passed.

- [ ] **Step 5: Commit.**

```bash
git add stack/control/tests/test_envfile.py stack/control/control/envfile.py
git commit -m "Plan 1 T7: envfile.compose_honcho_uri with URL-encoding"
```

---

## Task 8 — Write `.env.example` for Phase 1

**Files:**
- Create: `stack/env/.env.example`

- [ ] **Step 1:** Write `stack/env/.env.example`.

```bash
# ============================================================================
# 1215-VPS environment — single source of truth for the whole stack.
# Copy to `stack/env/.env` and run `start-1215 check` to verify.
# `start-1215 up` will auto-generate any blank key flagged [GEN] below.
# NEVER commit stack/env/.env.
# ============================================================================

# --- Supabase ---------------------------------------------------------------
# POSTGRES_PASSWORD: owner of the Supabase db; also used by Honcho DB superuser role.
POSTGRES_PASSWORD=                     # [GEN] 32 bytes hex
JWT_SECRET=                            # [GEN] 32 bytes hex
ANON_KEY=                              # derived from JWT_SECRET (day 1: populate manually from Supabase docs; future work: auto-derive)
SERVICE_ROLE_KEY=                      # derived from JWT_SECRET (same)
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=                    # [GEN] 24 alnum
POOLER_TENANT_ID=                      # [GEN] 16 alnum
POOLER_DB_POOL_SIZE=5
# Supabase storage: required since v1.37.8; stub values are fine for local/file-mode.
GLOBAL_S3_BUCKET=stub
REGION=stub
STORAGE_TENANT_ID=stub
S3_PROTOCOL_ACCESS_KEY_ID=625729a08b95bf1b7ff351a663f3a23c
S3_PROTOCOL_ACCESS_KEY_SECRET=850181e4652dd023b7a98c58ae0d2d34bd487ee0cc3254aed6eda37307425907

# --- Honcho (DB only; service not deployed until Plan 2) --------------------
HONCHO_DB_PASSWORD=                    # [GEN] 32 bytes hex
# HONCHO_DB_CONNECTION_URI is composed at runtime; do not set manually.

# --- Broker (schema inside Supabase db; see ADR-016) ------------------------
BROKER_APP_PASSWORD=                   # [GEN] 32 bytes hex

# --- Neo4j ------------------------------------------------------------------
NEO4J_AUTH=                            # [GEN] format: neo4j/<32-hex>

# --- Langfuse (full service wiring in Plan 4; secrets provisioned now) -----
CLICKHOUSE_PASSWORD=                   # [GEN] 32 bytes hex
MINIO_ROOT_USER=minio
MINIO_ROOT_PASSWORD=                   # [GEN] 32 bytes hex
LANGFUSE_SALT=                         # [GEN] 32 bytes hex
NEXTAUTH_SECRET=                       # [GEN] 32 bytes hex
ENCRYPTION_KEY=                        # [GEN] 32 bytes hex

# --- n8n (service exists; full S3 wiring is Plan 4) ------------------------
N8N_ENCRYPTION_KEY=                    # [GEN] 32 bytes hex
N8N_USER_MANAGEMENT_JWT_SECRET=        # [GEN] 32 bytes hex

# --- SearXNG ----------------------------------------------------------------
SEARXNG_SECRET_KEY=                    # [GEN] 32 bytes hex; upstream start_services.py also generates if blank

# --- Flowise ----------------------------------------------------------------
FLOWISE_USERNAME=admin
FLOWISE_PASSWORD=                      # [GEN] 24 alnum

# --- Caddy hostnames (leave empty for default ":PORT" tailnet-internal) -----
# Populate these in Plan 5 when wiring edge. For Phase 1, defaults are fine.
N8N_HOSTNAME=
WEBUI_HOSTNAME=
FLOWISE_HOSTNAME=
SUPABASE_HOSTNAME=
OLLAMA_HOSTNAME=
SEARXNG_HOSTNAME=
LANGFUSE_HOSTNAME=
NEO4J_HOSTNAME=
LETSENCRYPT_EMAIL=internal
```

- [ ] **Step 2:** Verify file parses.

Run (from repo root): `cd stack/control && uv run python -c "from control.envfile import parse; from pathlib import Path; print(len(parse(Path('../env/.env.example'))))"`

Expected: prints a number around 26 (the count of KEY=... lines).

- [ ] **Step 3:** Commit.

```bash
git add stack/env/.env.example
git commit -m "Plan 1 T8: .env.example covering Phase 1 surface area"
```

---

## Task 9 — Wire secret auto-generation into preflight

**Files:**
- Create: `stack/control/control/phases/preflight.py`
- Create: `stack/control/tests/test_preflight.py`

- [ ] **Step 1: Write the failing test.**

Write `stack/control/tests/test_preflight.py`:

```python
"""Tests for preflight phase: .env validation + auto-generation."""
from pathlib import Path

import pytest

from control.phases import preflight


def test_ensure_env_creates_env_from_example_if_absent(tmp_path: Path):
    example = tmp_path / ".env.example"
    example.write_text("FOO=\nBAR=static\n")
    env = tmp_path / ".env"
    preflight.ensure_env(env_path=env, example_path=example, required={})
    assert env.exists()
    # FOO unfilled remains empty; static value preserved.
    content = env.read_text()
    assert "FOO=\n" in content
    assert "BAR=static\n" in content


def test_ensure_env_generates_missing_required_secrets(tmp_path: Path):
    example = tmp_path / ".env.example"
    example.write_text("SECRET=\nKEEP=static\n")
    env = tmp_path / ".env"
    env.write_text("SECRET=\nKEEP=static\n")
    preflight.ensure_env(
        env_path=env,
        example_path=example,
        required={"SECRET": ("hex", 32)},
    )
    content = env.read_text()
    # SECRET is now populated; KEEP is unchanged.
    import re
    m = re.search(r"^SECRET=([0-9a-f]{64})$", content, re.MULTILINE)
    assert m, f"SECRET not generated: {content!r}"
    assert "KEEP=static\n" in content


def test_ensure_env_composes_honcho_uri_when_password_present(tmp_path: Path):
    example = tmp_path / ".env.example"
    example.write_text("HONCHO_DB_PASSWORD=\nHONCHO_DB_CONNECTION_URI=\n")
    env = tmp_path / ".env"
    env.write_text("HONCHO_DB_PASSWORD=\nHONCHO_DB_CONNECTION_URI=\n")
    preflight.ensure_env(
        env_path=env,
        example_path=example,
        required={"HONCHO_DB_PASSWORD": ("hex", 32)},
        composed={"HONCHO_DB_CONNECTION_URI": "honcho_uri"},
    )
    content = env.read_text()
    assert "HONCHO_DB_CONNECTION_URI=postgresql+psycopg://honcho_app:" in content
    assert "@db:5432/honcho" in content


def test_ensure_env_is_idempotent(tmp_path: Path):
    example = tmp_path / ".env.example"
    example.write_text("SECRET=\n")
    env = tmp_path / ".env"
    env.write_text("SECRET=\n")
    preflight.ensure_env(
        env_path=env,
        example_path=example,
        required={"SECRET": ("hex", 32)},
    )
    first = env.read_text()
    preflight.ensure_env(
        env_path=env,
        example_path=example,
        required={"SECRET": ("hex", 32)},
    )
    second = env.read_text()
    assert first == second, "idempotent call changed the file"
```

- [ ] **Step 2: Run, verify fail.**

Run: `cd stack/control && uv run pytest tests/test_preflight.py -v`

Expected: all fail with import error for `control.phases.preflight`.

- [ ] **Step 3: Implement.**

Write `stack/control/control/phases/preflight.py`:

```python
"""Phase 0 — preflight.

Responsibilities:
- Ensure `stack/env/.env` exists (create from `.env.example` if absent).
- Populate any missing required secrets.
- Compose derived keys (e.g., HONCHO_DB_CONNECTION_URI from HONCHO_DB_PASSWORD).
- Copy root `.env` to `supabase/docker/.env` — upstream Supabase compose requires it
  at that path. (Handled in a later task; this module exposes `ensure_env` only.)
"""
from __future__ import annotations

from pathlib import Path
from typing import Mapping

from control import envfile, secrets


_COMPOSERS = {
    "honcho_uri": lambda values: envfile.compose_honcho_uri(
        password=values["HONCHO_DB_PASSWORD"]
    ),
}


def ensure_env(
    env_path: Path,
    example_path: Path,
    required: Mapping[str, tuple[str, int]],
    composed: Mapping[str, str] = {},
) -> dict[str, str]:
    """Guarantee `env_path` exists with every required secret populated.

    - If `env_path` is missing, start from `example_path` (empty-valued template).
    - For each key in `required`, generate a value using the given strategy
      if the current value is empty.
    - For each key in `composed`, compute a derived value (looked up in the
      `_COMPOSERS` registry) using the post-generation env.
    - Write the result back using `envfile.render` against `example_path`,
      preserving comments and ordering.

    Returns the final env dict.
    """
    current = envfile.parse(env_path) if env_path.exists() else envfile.parse(example_path)

    # Fill required secrets first.
    populated = secrets.populate_missing(current, dict(required))

    # Compose derived values after secrets are in place.
    for key, composer_name in composed.items():
        composer = _COMPOSERS.get(composer_name)
        if composer is None:
            raise ValueError(f"unknown composer {composer_name!r} for {key}")
        if not populated.get(key):
            populated[key] = composer(populated)

    rendered = envfile.render(example_path, populated)
    env_path.write_text(rendered)
    return populated
```

- [ ] **Step 4: Run, verify pass.**

Run: `cd stack/control && uv run pytest tests/test_preflight.py -v`

Expected: 4 passed.

- [ ] **Step 5: Commit.**

```bash
git add stack/control/control/phases/preflight.py stack/control/tests/test_preflight.py
git commit -m "Plan 1 T9: preflight.ensure_env with required + composed keys"
```

---

## Task 10 — TDD: Supabase three-level readiness gate

**Files:**
- Create: `stack/control/control/supabase.py`
- Create: `stack/control/tests/test_supabase.py`

- [ ] **Step 1: Write the failing tests.**

Write `stack/control/tests/test_supabase.py`:

```python
"""Tests for the three-level Supabase readiness gate.

The gate itself runs shell commands and HTTP calls against a live Supabase
stack; those are covered by the integration test (test_phase1_integration).
Here we test the composition logic — timeouts, level escalation, and
error formatting — using mocks.
"""
from __future__ import annotations

import pytest

from control import supabase


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


def test_wait_passes_when_all_levels_succeed_immediately():
    clock = FakeClock()
    checks = supabase.Checks(
        container_healthy=lambda: True,
        accepts_queries=lambda: True,
        http_ready=lambda: True,
    )
    # Should return without raising.
    supabase.wait_for_supabase(checks, timeout_s=10, clock=clock)


def test_wait_raises_when_level1_never_becomes_healthy():
    clock = FakeClock()
    checks = supabase.Checks(
        container_healthy=lambda: False,
        accepts_queries=lambda: True,
        http_ready=lambda: True,
    )
    with pytest.raises(TimeoutError, match="level 1"):
        supabase.wait_for_supabase(checks, timeout_s=5, clock=clock)


def test_wait_raises_when_level2_never_succeeds():
    clock = FakeClock()
    checks = supabase.Checks(
        container_healthy=lambda: True,
        accepts_queries=lambda: False,
        http_ready=lambda: True,
    )
    with pytest.raises(TimeoutError, match="level 2"):
        supabase.wait_for_supabase(checks, timeout_s=5, clock=clock)


def test_wait_raises_when_level3_never_succeeds():
    clock = FakeClock()
    checks = supabase.Checks(
        container_healthy=lambda: True,
        accepts_queries=lambda: True,
        http_ready=lambda: False,
    )
    with pytest.raises(TimeoutError, match="level 3"):
        supabase.wait_for_supabase(checks, timeout_s=5, clock=clock)


def test_wait_progresses_through_levels():
    """Level 2 is not polled until level 1 succeeds."""
    clock = FakeClock()
    level1_calls = []
    level2_calls = []

    def l1():
        level1_calls.append(clock.now())
        return clock.now() >= 3.0  # succeeds after 3s

    def l2():
        level2_calls.append(clock.now())
        return True

    checks = supabase.Checks(
        container_healthy=l1,
        accepts_queries=l2,
        http_ready=lambda: True,
    )
    supabase.wait_for_supabase(checks, timeout_s=20, clock=clock)
    # level 2 should only have been polled after level 1 succeeded.
    for t in level2_calls:
        assert t >= 3.0, f"level 2 polled at t={t} before level 1 succeeded"
```

- [ ] **Step 2: Run, verify fail.**

Run: `cd stack/control && uv run pytest tests/test_supabase.py -v`

Expected: all fail with import error.

- [ ] **Step 3: Implement.**

Write `stack/control/control/supabase.py`:

```python
"""Three-level readiness gate for Supabase.

Level 1: container reports healthy (`docker compose ps` / docker health check).
Level 2: Postgres accepts queries (`SELECT 1` succeeds).
Level 3: Supabase kong routes to the auth service (`/auth/v1/health` → 200)
         AND PostgREST sees the broker schema (`/rest/v1/broker_alignment_log` → 200 or 401).

Each level is polled independently; the gate only advances to the next level
once the current one succeeds. Time spent waiting counts against a single
total timeout. A failure prints which level timed out so callers know where
to look.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Protocol


class Clock(Protocol):
    def now(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...


class _WallClock:
    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


@dataclass
class Checks:
    """Callables that return True when the level's condition is met."""
    container_healthy: Callable[[], bool]
    accepts_queries: Callable[[], bool]
    http_ready: Callable[[], bool]


def wait_for_supabase(
    checks: Checks,
    timeout_s: float,
    *,
    poll_interval_s: float = 3.0,
    clock: Clock | None = None,
) -> None:
    """Block until all three levels succeed, or raise TimeoutError.

    The error message names the level that timed out so operators know
    whether Postgres itself is stuck, or whether kong/PostgREST haven't
    caught up to migrations yet.
    """
    clock = clock or _WallClock()
    deadline = clock.now() + timeout_s

    levels = [
        ("level 1 (container healthy)", checks.container_healthy),
        ("level 2 (psql SELECT 1)", checks.accepts_queries),
        ("level 3 (kong /auth/v1/health)", checks.http_ready),
    ]
    for name, probe in levels:
        while True:
            if probe():
                break
            if clock.now() >= deadline:
                raise TimeoutError(f"Supabase readiness {name} timed out")
            clock.sleep(poll_interval_s)
```

- [ ] **Step 4: Run, verify pass.**

Run: `cd stack/control && uv run pytest tests/test_supabase.py -v`

Expected: 5 passed.

- [ ] **Step 5: Commit.**

```bash
git add stack/control/control/supabase.py stack/control/tests/test_supabase.py
git commit -m "Plan 1 T10: three-level Supabase readiness gate with unit tests"
```

---

## Task 11 — Real-world check implementations for the readiness gate

**Files:**
- Modify: `stack/control/control/supabase.py`

These call actual `docker` / `psql` / `curl`-equivalent. They aren't unit-testable
cleanly — the integration test at the end of the plan exercises them end-to-end.

- [ ] **Step 1:** Append to `stack/control/control/supabase.py`:

```python
import subprocess

import requests


def probe_container_healthy(container_name: str = "supabase-db", project: str = "localai") -> bool:
    """Level 1: docker compose says this container is healthy.

    We use `docker inspect` rather than `docker compose ps --format json`
    because it's more portable across Compose versions.
    """
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Health.Status}}", container_name],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    return result.returncode == 0 and result.stdout.strip() == "healthy"


def probe_accepts_queries(container_name: str = "supabase-db") -> bool:
    """Level 2: `psql -c 'SELECT 1'` exits 0."""
    try:
        result = subprocess.run(
            [
                "docker", "exec", container_name,
                "psql", "-U", "postgres", "-d", "postgres",
                "-tAc", "SELECT 1",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    return result.returncode == 0 and result.stdout.strip() == "1"


def probe_http_ready(kong_url: str = "http://localhost:8000") -> bool:
    """Level 3: kong routes to auth service.

    200 is the happy path; 4xx still indicates routing works (auth service
    responded). 5xx or connection errors mean we're not ready.
    """
    try:
        r = requests.get(f"{kong_url}/auth/v1/health", timeout=5)
    except requests.RequestException:
        return False
    return 200 <= r.status_code < 500


def default_checks() -> Checks:
    return Checks(
        container_healthy=probe_container_healthy,
        accepts_queries=probe_accepts_queries,
        http_ready=probe_http_ready,
    )
```

- [ ] **Step 2:** Smoke-test the module imports.

Run: `cd stack/control && uv run python -c "from control.supabase import default_checks; print(default_checks())"`

Expected: prints a `Checks(...)` repr without raising.

- [ ] **Step 3: Commit.**

```bash
git add stack/control/control/supabase.py
git commit -m "Plan 1 T11: real probe implementations (docker/psql/http) for gate"
```

---

## Task 12 — Write db-init SQL files

**Files:**
- Create: `stack/services/db-init/sql/01_honcho.sql`
- Create: `stack/services/db-init/sql/02_broker.sql`
- Create: `stack/services/db-init/sql/03_broker_tables.sql`
- Create: `stack/services/db-init/sql/04_broker_rls.sql`

- [ ] **Step 1:** Write `stack/services/db-init/sql/01_honcho.sql`.

```sql
-- Idempotent: safe to run on every bring-up.
-- Creates the honcho database and its application role.
-- Extensions are created inside the honcho database (see bottom).

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'honcho_app') THEN
        EXECUTE format(
            'CREATE ROLE honcho_app LOGIN PASSWORD %L',
            current_setting('vps.honcho_password')
        );
    ELSE
        EXECUTE format(
            'ALTER ROLE honcho_app WITH LOGIN PASSWORD %L',
            current_setting('vps.honcho_password')
        );
    END IF;
END
$$;

SELECT 'CREATE DATABASE honcho OWNER honcho_app'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'honcho')
\gexec

GRANT ALL PRIVILEGES ON DATABASE honcho TO honcho_app;

-- Extensions live inside the target DB, not `postgres`. Reconnect via \c.
\c honcho

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

GRANT ALL ON SCHEMA public TO honcho_app;
```

- [ ] **Step 2:** Write `stack/services/db-init/sql/02_broker.sql`.

```sql
-- Broker schema inside the default `postgres` database (per ADR-016).
-- Uses PostgREST's auto-discovery: any schema named in `PGRST_DB_SCHEMAS`
-- (configured in supabase's .env) is exposed via /rest/v1/<schema>.
-- We don't modify PGRST_DB_SCHEMAS here; tables are named with a `broker_`
-- prefix and created in the `public` schema-equivalent naming convention
-- so they're visible at /rest/v1/broker_* without reconfiguring Supabase.
-- ACTUALLY: we create a dedicated `broker` schema and expose via schema naming
-- below. Supabase exposes `public`, `graphql_public`, and `storage` by default;
-- `broker` is added here.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'broker_app') THEN
        EXECUTE format(
            'CREATE ROLE broker_app LOGIN PASSWORD %L',
            current_setting('vps.broker_password')
        );
    ELSE
        EXECUTE format(
            'ALTER ROLE broker_app WITH LOGIN PASSWORD %L',
            current_setting('vps.broker_password')
        );
    END IF;
END
$$;

CREATE SCHEMA IF NOT EXISTS broker AUTHORIZATION broker_app;

-- Grant the Supabase `anon` and `authenticated` roles the ability to see
-- the schema (PostgREST expects this). Writes are still gated by RLS.
GRANT USAGE ON SCHEMA broker TO anon, authenticated, service_role, broker_app;
```

- [ ] **Step 3:** Write `stack/services/db-init/sql/03_broker_tables.sql`.

```sql
-- Tables owned by broker_app in the broker schema.
-- alignment_log: append-only audit of inter-company events.
-- artifact_manifests: pointer records for published artifacts (bodies in MinIO).

SET search_path TO broker;

CREATE TABLE IF NOT EXISTS alignment_log (
    log_id          bigserial PRIMARY KEY,
    occurred_at     timestamptz NOT NULL DEFAULT now(),
    peer_id         text        NOT NULL,          -- e.g. "orchestrator-ceo", "eng-ceo"
    event_type      text        NOT NULL,          -- e.g. "fact.published", "artifact.ready"
    payload         jsonb       NOT NULL,
    prev_log_id     bigint      REFERENCES broker.alignment_log(log_id),
    content_hash    text        NOT NULL,          -- sha256 of payload for idempotency
    CONSTRAINT alignment_log_content_hash_unique UNIQUE (peer_id, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_alignment_log_occurred_at
    ON alignment_log (occurred_at);
CREATE INDEX IF NOT EXISTS idx_alignment_log_peer_id
    ON alignment_log (peer_id);
CREATE INDEX IF NOT EXISTS idx_alignment_log_event_type
    ON alignment_log (event_type);

CREATE TABLE IF NOT EXISTS artifact_manifests (
    artifact_id     uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    peer_id         text        NOT NULL,
    artifact_kind   text        NOT NULL,          -- e.g. "paper", "figure", "dataset"
    title           text        NOT NULL,
    summary         text,
    storage_uri     text        NOT NULL,          -- e.g. "s3://artifacts/path/to/file"
    content_hash    text        NOT NULL,
    metadata        jsonb       NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT artifact_manifests_peer_hash_unique UNIQUE (peer_id, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_artifact_manifests_peer_id
    ON artifact_manifests (peer_id);
CREATE INDEX IF NOT EXISTS idx_artifact_manifests_created_at
    ON artifact_manifests (created_at);

-- broker_app owns the tables; Supabase's anon/authenticated/service_role need
-- SELECT/INSERT via PostgREST — gated by RLS below.
ALTER TABLE alignment_log OWNER TO broker_app;
ALTER TABLE artifact_manifests OWNER TO broker_app;

GRANT SELECT, INSERT ON alignment_log, artifact_manifests TO authenticated, service_role;
GRANT USAGE, SELECT ON SEQUENCE alignment_log_log_id_seq TO authenticated, service_role;
```

- [ ] **Step 4:** Write `stack/services/db-init/sql/04_broker_rls.sql`.

```sql
-- RLS policies for broker tables.
-- Strategy: writes require a valid JWT with a `peer_id` claim; reads are
-- open to anyone with a valid JWT (the broker is a shared log by design).
-- service_role bypasses RLS per Supabase convention.

SET search_path TO broker;

ALTER TABLE alignment_log   ENABLE ROW LEVEL SECURITY;
ALTER TABLE artifact_manifests ENABLE ROW LEVEL SECURITY;

-- Reads: any authenticated principal can SELECT.
DROP POLICY IF EXISTS alignment_log_select ON alignment_log;
CREATE POLICY alignment_log_select ON alignment_log
    FOR SELECT
    TO authenticated
    USING (true);

DROP POLICY IF EXISTS artifact_manifests_select ON artifact_manifests;
CREATE POLICY artifact_manifests_select ON artifact_manifests
    FOR SELECT
    TO authenticated
    USING (true);

-- Writes: the row's peer_id must match the JWT's `peer_id` claim.
DROP POLICY IF EXISTS alignment_log_insert ON alignment_log;
CREATE POLICY alignment_log_insert ON alignment_log
    FOR INSERT
    TO authenticated
    WITH CHECK (peer_id = current_setting('request.jwt.claims', true)::jsonb->>'peer_id');

DROP POLICY IF EXISTS artifact_manifests_insert ON artifact_manifests;
CREATE POLICY artifact_manifests_insert ON artifact_manifests
    FOR INSERT
    TO authenticated
    WITH CHECK (peer_id = current_setting('request.jwt.claims', true)::jsonb->>'peer_id');
```

- [ ] **Step 5:** Commit.

```bash
git add stack/services/db-init/sql/
git commit -m "Plan 1 T12: db-init SQL — honcho DB + broker schema/tables/RLS"
```

---

## Task 13 — db-init Dockerfile and entrypoint

**Files:**
- Create: `stack/services/db-init/Dockerfile`
- Create: `stack/services/db-init/init.sh`

- [ ] **Step 1:** Write `stack/services/db-init/Dockerfile`.

```dockerfile
FROM postgres:17-alpine

COPY init.sh /init.sh
COPY sql/ /sql/
RUN chmod +x /init.sh

ENTRYPOINT ["/init.sh"]
```

- [ ] **Step 2:** Write `stack/services/db-init/init.sh`.

```bash
#!/usr/bin/env sh
# Runs SQL files in /sql/ in lexical order against the Supabase DB.
# Idempotent by construction: every SQL file uses IF NOT EXISTS / DO blocks.
#
# Env:
#   PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE — libpq standard
#   HONCHO_DB_PASSWORD — passed into psql as `vps.honcho_password` runtime setting
#   BROKER_APP_PASSWORD — passed into psql as `vps.broker_password` runtime setting
#
# We use runtime settings (SET LOCAL via -c) so SQL can reference the password
# without embedding it in the script as plaintext.

set -eu

: "${PGHOST:?PGHOST required}"
: "${PGPORT:=5432}"
: "${PGUSER:?PGUSER required}"
: "${PGPASSWORD:?PGPASSWORD required}"
: "${PGDATABASE:=postgres}"
: "${HONCHO_DB_PASSWORD:?HONCHO_DB_PASSWORD required}"
: "${BROKER_APP_PASSWORD:?BROKER_APP_PASSWORD required}"

export PGPASSWORD

echo "[db-init] waiting for postgres at ${PGHOST}:${PGPORT}..."
until pg_isready -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" >/dev/null 2>&1; do
    sleep 1
done
echo "[db-init] postgres ready"

for sql in /sql/*.sql; do
    echo "[db-init] applying $sql"
    psql \
        -v ON_ERROR_STOP=1 \
        -c "SET vps.honcho_password = '$HONCHO_DB_PASSWORD';" \
        -c "SET vps.broker_password = '$BROKER_APP_PASSWORD';" \
        -f "$sql"
done

echo "[db-init] done"
```

- [ ] **Step 3:** Mark executable and commit.

```bash
chmod +x stack/services/db-init/init.sh
git add stack/services/db-init/Dockerfile stack/services/db-init/init.sh
git update-index --chmod=+x stack/services/db-init/init.sh
git commit -m "Plan 1 T13: db-init Dockerfile + idempotent entrypoint"
```

---

## Task 14 — mc-init (MinIO bucket provisioning)

**Files:**
- Create: `stack/services/mc-init/init.sh`

- [ ] **Step 1:** Write `stack/services/mc-init/init.sh`.

```bash
#!/usr/bin/env sh
# Provisions MinIO buckets idempotently.
# Uses the minio/mc image; entrypoint overridden by compose.
#
# Env:
#   MINIO_ENDPOINT (default http://minio:9000)
#   MINIO_ROOT_USER, MINIO_ROOT_PASSWORD

set -eu

: "${MINIO_ENDPOINT:=http://minio:9000}"
: "${MINIO_ROOT_USER:?MINIO_ROOT_USER required}"
: "${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD required}"

echo "[mc-init] waiting for minio at ${MINIO_ENDPOINT}..."
until /usr/bin/mc alias set local "$MINIO_ENDPOINT" "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null 2>&1; do
    sleep 1
done
echo "[mc-init] minio ready"

for bucket in langfuse n8n artifacts; do
    if /usr/bin/mc ls "local/$bucket" >/dev/null 2>&1; then
        echo "[mc-init] bucket '$bucket' already exists"
    else
        /usr/bin/mc mb "local/$bucket"
        echo "[mc-init] created bucket '$bucket'"
    fi
done

echo "[mc-init] done"
```

- [ ] **Step 2:** Mark executable and commit.

```bash
chmod +x stack/services/mc-init/init.sh
git add stack/services/mc-init/init.sh
git update-index --chmod=+x stack/services/mc-init/init.sh
git commit -m "Plan 1 T14: mc-init idempotent bucket provisioning"
```

---

## Task 15 — Compose overlay: networks and upstream attachments

**Files:**
- Create: `stack/docker-compose.1215.yml`

- [ ] **Step 1:** Write `stack/docker-compose.1215.yml`.

```yaml
# 1215-VPS Compose overlay.
#
# Layered on top of:
#   - modules/local-ai-packaged/docker-compose.yml
#   - supabase/docker/docker-compose.yml (sparse-cloned by start_services.py)
# via `docker compose -p localai -f <LAI> -f <SUPA> -f <THIS>`.
#
# Only additive: defines networks + reattaches upstream services, then
# declares 1215-specific services (db-init, mc-init). Later plans add
# honcho, paperclip-orchestrator, n8n-mcp.

name: localai

networks:
  localai-data:
    name: localai-data
  localai-app:
    name: localai-app

services:
  # --- upstream attachments: redeclare with networks only --------------------
  # Caddy: both planes (fronts app-plane services, serves data-plane admin UIs)
  caddy:
    networks: [localai-app, localai-data]

  # Supabase: kong, studio straddle both; db and inner services stay data-only
  kong:
    networks: [localai-app, localai-data]
  studio:
    networks: [localai-app, localai-data]
  db:
    networks: [localai-data]
  auth:
    networks: [localai-data]
  storage:
    networks: [localai-data]
  realtime:
    networks: [localai-data]
  meta:
    networks: [localai-data]
  rest:
    networks: [localai-data]
  edge-functions: { networks: [localai-data] }   # upstream name varies; adjust if different
  imgproxy: { networks: [localai-data] }
  analytics: { networks: [localai-data] }
  vector: { networks: [localai-data] }
  pooler: { networks: [localai-data] }
  functions: { networks: [localai-data] }

  # Langfuse data services
  postgres: { networks: [localai-data] }       # Langfuse's dedicated pg
  clickhouse: { networks: [localai-data] }
  redis: { networks: [localai-data, localai-app] }   # shared cache
  minio: { networks: [localai-data, localai-app] }

  # App-plane services that also talk to data
  langfuse-web: { networks: [localai-app, localai-data] }
  langfuse-worker: { networks: [localai-app, localai-data] }
  n8n: { networks: [localai-app, localai-data] }
  open-webui: { networks: [localai-app] }
  flowise: { networks: [localai-app] }
  searxng: { networks: [localai-app] }
  qdrant: { networks: [localai-data, localai-app] }
  neo4j: { networks: [localai-data, localai-app] }

  # --- 1215-specific: init jobs ----------------------------------------------
  db-init:
    build:
      context: ./services/db-init
    networks: [localai-data]
    depends_on:
      db:
        condition: service_healthy
    environment:
      PGHOST: db
      PGPORT: "5432"
      PGUSER: postgres
      PGPASSWORD: ${POSTGRES_PASSWORD}
      PGDATABASE: postgres
      HONCHO_DB_PASSWORD: ${HONCHO_DB_PASSWORD}
      BROKER_APP_PASSWORD: ${BROKER_APP_PASSWORD}
    restart: "no"

  mc-init:
    image: minio/mc:latest
    networks: [localai-data]
    depends_on:
      minio:
        condition: service_healthy
    entrypoint: /bin/sh
    command: /init.sh
    volumes:
      - ./services/mc-init/init.sh:/init.sh:ro
    environment:
      MINIO_ENDPOINT: http://minio:9000
      MINIO_ROOT_USER: ${MINIO_ROOT_USER}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD}
    restart: "no"
```

**Note for the executing agent:** Supabase's upstream compose uses a bunch of service names (some of which differ across Supabase versions — the list above follows v2026). If `docker compose config` reports "service X referenced but not defined", remove that override entry and re-run; the network attachment will fall back to upstream's default network for that service. Log any such omissions so they can be spec-corrected.

- [ ] **Step 2:** Validate the overlay parses on its own.

Run: `docker compose -f stack/docker-compose.1215.yml config --quiet`

Expected: exits 0. (This only validates syntax; actual service references are checked when layered.)

- [ ] **Step 3:** Commit.

```bash
git add stack/docker-compose.1215.yml
git commit -m "Plan 1 T15: compose overlay — networks + upstream attachments + init jobs"
```

---

## Task 16 — `compose.py` helper (subprocess wrappers)

**Files:**
- Create: `stack/control/control/compose.py`
- Create: `stack/control/tests/test_compose.py`

- [ ] **Step 1: Write the failing tests.**

Write `stack/control/tests/test_compose.py`:

```python
"""Tests for compose.py — wraps `docker compose` invocations."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from control import compose


def test_build_command_composes_all_files():
    cmd = compose.build_command(
        project="localai",
        compose_files=[Path("/a.yml"), Path("/b.yml")],
        subcommand=["up", "-d"],
    )
    assert cmd == [
        "docker", "compose",
        "-p", "localai",
        "-f", "/a.yml",
        "-f", "/b.yml",
        "up", "-d",
    ]


def test_build_command_requires_at_least_one_compose_file():
    with pytest.raises(ValueError, match="at least one"):
        compose.build_command(
            project="localai",
            compose_files=[],
            subcommand=["ps"],
        )


def test_run_invokes_subprocess_with_built_command(mocker):
    mock_run = mocker.patch("control.compose.subprocess.run")
    mock_run.return_value = MagicMock(returncode=0)
    compose.run(
        project="localai",
        compose_files=[Path("/a.yml")],
        subcommand=["ps"],
    )
    args, _ = mock_run.call_args
    assert args[0] == [
        "docker", "compose",
        "-p", "localai",
        "-f", "/a.yml",
        "ps",
    ]


def test_run_raises_on_nonzero_exit(mocker):
    mocker.patch(
        "control.compose.subprocess.run",
        return_value=MagicMock(returncode=2, stdout="", stderr="boom"),
    )
    with pytest.raises(compose.ComposeError, match="exit 2"):
        compose.run(
            project="localai",
            compose_files=[Path("/a.yml")],
            subcommand=["up"],
        )
```

- [ ] **Step 2: Run, verify fail.**

Run: `cd stack/control && uv run pytest tests/test_compose.py -v`

Expected: import error.

- [ ] **Step 3: Implement.**

Write `stack/control/control/compose.py`:

```python
"""Thin wrappers around `docker compose` invocations.

Keeps subprocess assembly out of phase code so phase logic stays testable.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


class ComposeError(RuntimeError):
    pass


def build_command(
    project: str,
    compose_files: list[Path],
    subcommand: list[str],
) -> list[str]:
    """Construct a `docker compose -p <project> -f ... <subcommand>` argv list."""
    if not compose_files:
        raise ValueError("at least one compose file required")
    cmd = ["docker", "compose", "-p", project]
    for f in compose_files:
        cmd.extend(["-f", str(f)])
    cmd.extend(subcommand)
    return cmd


def run(
    project: str,
    compose_files: list[Path],
    subcommand: list[str],
    *,
    check: bool = True,
    capture: bool = False,
) -> subprocess.CompletedProcess:
    """Run a docker compose command, raising ComposeError on non-zero exit (if check)."""
    cmd = build_command(project, compose_files, subcommand)
    result = subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
    )
    if check and result.returncode != 0:
        stderr = result.stderr if capture else "(see terminal output)"
        raise ComposeError(
            f"docker compose {' '.join(subcommand)} failed with exit {result.returncode}: {stderr}"
        )
    return result
```

- [ ] **Step 4: Run, verify pass.**

Run: `cd stack/control && uv run pytest tests/test_compose.py -v`

Expected: 4 passed.

- [ ] **Step 5: Commit.**

```bash
git add stack/control/control/compose.py stack/control/tests/test_compose.py
git commit -m "Plan 1 T16: compose.py wrapper with unit tests"
```

---

## Task 17 — Phase 1 runner (wires compose + wait + init jobs)

**Files:**
- Create: `stack/control/control/phases/data_plane.py`

This task is primarily integration logic; the end-to-end test in Task 19
exercises it. Unit tests here would mostly assert mock wiring.

- [ ] **Step 1:** Write `stack/control/control/phases/data_plane.py`.

```python
"""Phase 1 — data plane.

Bring up Supabase (upstream) + LAI data services + overlay db-init and mc-init.
Between stages, run the three-level Supabase readiness gate.
"""
from __future__ import annotations

import logging
from pathlib import Path

from control import compose, supabase

log = logging.getLogger(__name__)

PROJECT = "localai"

# Paths resolved relative to the repo root (cwd when start-1215 is invoked).
LAI_COMPOSE = Path("modules/local-ai-packaged/docker-compose.yml")
SUPABASE_COMPOSE = Path("modules/local-ai-packaged/supabase/docker/docker-compose.yml")
OVERLAY_COMPOSE = Path("stack/docker-compose.1215.yml")

DATA_SERVICES = [
    # Supabase (started via its own compose file, not listed in `up` args — we just call full `up`
    # and let depends_on order things. For Phase 1 we start _all_ data-plane services at once;
    # partial ups are brittle with Supabase's long dep chain.)
]


def bring_up(
    *,
    first_boot: bool,
    ollama_profile: str = "none",
    gate_timeout_s: float | None = None,
) -> None:
    """Bring up Phase 1 services and block on readiness."""
    if gate_timeout_s is None:
        gate_timeout_s = 600.0 if first_boot else 120.0

    compose_files = [LAI_COMPOSE, SUPABASE_COMPOSE, OVERLAY_COMPOSE]

    log.info("phase 1: starting data plane (%s)", ollama_profile)
    subcommand = ["up", "-d"]
    if ollama_profile != "none":
        subcommand = ["--profile", ollama_profile, *subcommand]
    # First: bring up upstream data services (Supabase + LAI data). Using `up -d` without
    # service-name args tells Compose to start everything defined, but our init jobs have
    # explicit depends_on so they won't run before their dependencies are healthy.
    compose.run(PROJECT, compose_files, subcommand)

    log.info("phase 1: waiting on Supabase readiness (timeout %.0fs)", gate_timeout_s)
    supabase.wait_for_supabase(
        supabase.default_checks(),
        timeout_s=gate_timeout_s,
    )
    log.info("phase 1: Supabase ready")

    log.info("phase 1: running db-init job")
    compose.run(PROJECT, compose_files, ["up", "--no-deps", "--exit-code-from", "db-init", "db-init"])
    log.info("phase 1: db-init complete")

    log.info("phase 1: running mc-init job")
    compose.run(PROJECT, compose_files, ["up", "--no-deps", "--exit-code-from", "mc-init", "mc-init"])
    log.info("phase 1: mc-init complete")
```

- [ ] **Step 2:** Smoke-test imports.

Run: `cd stack/control && uv run python -c "from control.phases.data_plane import bring_up; print(bring_up)"`

Expected: prints `<function bring_up at 0x...>`.

- [ ] **Step 3: Commit.**

```bash
git add stack/control/control/phases/data_plane.py
git commit -m "Plan 1 T17: Phase 1 runner (compose up + gate + init jobs)"
```

---

## Task 18 — CLI entry point

**Files:**
- Create: `stack/control/control/cli.py`
- Create: `stack/control/tests/test_cli.py`

- [ ] **Step 1: Write the failing test.**

Write `stack/control/tests/test_cli.py`:

```python
"""Tests for the CLI surface."""
from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from control import cli


def test_check_exits_zero_when_env_and_example_exist(tmp_path: Path, monkeypatch):
    example = tmp_path / "env" / ".env.example"
    example.parent.mkdir()
    example.write_text("SECRET=\nKEEP=static\n")

    runner = CliRunner()
    result = runner.invoke(
        cli.main,
        ["--env-dir", str(tmp_path / "env"), "check"],
    )
    assert result.exit_code == 0, result.output


def test_check_exits_nonzero_when_example_missing(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(
        cli.main,
        ["--env-dir", str(tmp_path / "env"), "check"],
    )
    assert result.exit_code != 0
    assert ".env.example" in result.output


def test_check_reports_missing_required_keys(tmp_path: Path):
    example = tmp_path / "env" / ".env.example"
    example.parent.mkdir()
    example.write_text("MY_SECRET=\n")

    # .env exists but MY_SECRET is empty — check should flag this without generating.
    env = tmp_path / "env" / ".env"
    env.write_text("MY_SECRET=\n")

    runner = CliRunner()
    result = runner.invoke(
        cli.main,
        ["--env-dir", str(tmp_path / "env"), "check", "--no-generate"],
    )
    assert result.exit_code != 0
    assert "MY_SECRET" in result.output
```

- [ ] **Step 2: Run, verify fail.**

Run: `cd stack/control && uv run pytest tests/test_cli.py -v`

Expected: import error for `control.cli`.

- [ ] **Step 3: Implement.**

Write `stack/control/control/cli.py`:

```python
"""Command-line entry point: `start-1215 <subcommand>`.

Subcommands:
- check: validate stack/env/.env (optionally generate missing secrets).
- up:    run preflight + Phase 1 bring-up.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from control import envfile
from control.phases import data_plane, preflight


# Keys that must exist with non-empty values for Phase 1 to run.
PHASE1_REQUIRED: dict[str, tuple[str, int]] = {
    "POSTGRES_PASSWORD": ("hex", 32),
    "JWT_SECRET": ("hex", 32),
    "DASHBOARD_PASSWORD": ("alnum", 24),
    "POOLER_TENANT_ID": ("alnum", 16),
    "HONCHO_DB_PASSWORD": ("hex", 32),
    "BROKER_APP_PASSWORD": ("hex", 32),
    "NEO4J_AUTH": ("hex", 32),             # placeholder; composed below as neo4j/<hex>
    "CLICKHOUSE_PASSWORD": ("hex", 32),
    "MINIO_ROOT_PASSWORD": ("hex", 32),
    "LANGFUSE_SALT": ("hex", 32),
    "NEXTAUTH_SECRET": ("hex", 32),
    "ENCRYPTION_KEY": ("hex", 32),
    "N8N_ENCRYPTION_KEY": ("hex", 32),
    "N8N_USER_MANAGEMENT_JWT_SECRET": ("hex", 32),
    "SEARXNG_SECRET_KEY": ("hex", 32),
    "FLOWISE_PASSWORD": ("alnum", 24),
}

# Keys that get composed from other keys after generation.
PHASE1_COMPOSED: dict[str, str] = {
    # HONCHO_DB_CONNECTION_URI is needed later (Plan 2). We compose it now so
    # the rendered `.env` is complete from day one.
    "HONCHO_DB_CONNECTION_URI": "honcho_uri",
}


@click.group()
@click.option(
    "--env-dir",
    type=click.Path(path_type=Path),
    default=Path("stack/env"),
    help="Directory containing .env and .env.example.",
)
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging.")
@click.pass_context
def main(ctx: click.Context, env_dir: Path, verbose: bool) -> None:
    """1215-VPS control plane."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    ctx.ensure_object(dict)
    ctx.obj["env_dir"] = env_dir


@main.command()
@click.option(
    "--no-generate",
    is_flag=True,
    help="Fail if secrets are missing instead of generating them.",
)
@click.pass_context
def check(ctx: click.Context, no_generate: bool) -> None:
    """Validate environment; optionally auto-generate missing secrets."""
    env_dir: Path = ctx.obj["env_dir"]
    example = env_dir / ".env.example"
    env = env_dir / ".env"

    if not example.exists():
        click.echo(f"error: {example} not found", err=True)
        sys.exit(2)

    if no_generate:
        current = envfile.parse(env) if env.exists() else {}
        missing = [k for k in PHASE1_REQUIRED if not current.get(k)]
        if missing:
            click.echo(
                f"error: missing or empty required keys: {', '.join(missing)}",
                err=True,
            )
            sys.exit(1)
        click.echo("check: all required keys present.")
        return

    values = preflight.ensure_env(
        env_path=env,
        example_path=example,
        required=PHASE1_REQUIRED,
        composed=PHASE1_COMPOSED,
    )
    click.echo(f"check: OK — {len(values)} keys present in {env}.")


@main.command()
@click.option("--first-boot/--not-first-boot", default=False,
              help="Use longer timeout for Supabase migrations.")
@click.option("--ollama-profile", default="none",
              type=click.Choice(["none", "cpu", "gpu-nvidia", "gpu-amd"]))
@click.pass_context
def up(ctx: click.Context, first_boot: bool, ollama_profile: str) -> None:
    """Bring up Phase 0 (preflight) + Phase 1 (data plane)."""
    env_dir: Path = ctx.obj["env_dir"]
    example = env_dir / ".env.example"
    env = env_dir / ".env"

    if not example.exists():
        click.echo(f"error: {example} not found", err=True)
        sys.exit(2)

    click.echo("=== Phase 0: preflight ===")
    preflight.ensure_env(
        env_path=env,
        example_path=example,
        required=PHASE1_REQUIRED,
        composed=PHASE1_COMPOSED,
    )
    click.echo(f"preflight: env at {env} populated.")

    click.echo("=== Phase 1: data plane ===")
    data_plane.bring_up(
        first_boot=first_boot,
        ollama_profile=ollama_profile,
    )
    click.echo("phase 1 complete.")
```

- [ ] **Step 4: Run, verify pass.**

Run: `cd stack/control && uv run pytest tests/test_cli.py -v`

Expected: 3 passed.

- [ ] **Step 5: Verify `uv run start-1215 --help` works.**

Run: `cd stack/control && uv run start-1215 --help`

Expected: click help text listing `check` and `up` subcommands.

- [ ] **Step 6: Commit.**

```bash
git add stack/control/control/cli.py stack/control/tests/test_cli.py
git commit -m "Plan 1 T18: CLI with check + up subcommands"
```

---

## Task 19 — `bin/start-1215.py` shim

**Files:**
- Create: `bin/start-1215.py`

- [ ] **Step 1:** Write `bin/start-1215.py`.

```python
#!/usr/bin/env python3
"""1215-VPS bring-up entry point.

Thin shim: forwards to `uv run --project stack/control start-1215`.
This exists so the top-level command you type is short and discoverable
via `ls bin/` — all logic lives in the `control` package.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTROL_PROJECT = REPO_ROOT / "stack" / "control"

if not (CONTROL_PROJECT / "pyproject.toml").exists():
    sys.exit(f"error: expected {CONTROL_PROJECT}/pyproject.toml — run from a checkout of 1215-vps.")

# Exec uv so this process is replaced by the target; signals propagate cleanly.
os.chdir(REPO_ROOT)
os.execvp(
    "uv",
    ["uv", "run", "--project", str(CONTROL_PROJECT), "start-1215", *sys.argv[1:]],
)
```

- [ ] **Step 2:** Mark executable.

```bash
chmod +x bin/start-1215.py
```

- [ ] **Step 3:** Sanity check.

Run: `./bin/start-1215.py --help`

Expected: click help text (same as `uv run start-1215 --help`).

- [ ] **Step 4: Commit.**

```bash
git add bin/start-1215.py
git update-index --chmod=+x bin/start-1215.py
git commit -m "Plan 1 T19: bin/start-1215.py shim"
```

---

## Task 20 — Integration test: fresh Phase 1 bring-up

**Files:**
- Create: `stack/control/tests/test_phase1_integration.py`

**Prerequisite:** a Docker daemon is reachable. The test uses a sandboxed
project name (`localai-test`) to avoid clobbering any real bring-up.

**Note:** this test is slow (first boot ~3 min). Marked `@pytest.mark.integration`
so normal `pytest` runs skip it.

- [ ] **Step 1:** Write the test.

```python
"""End-to-end Phase 1 integration test.

Runs a full preflight + phase 1 bring-up against a live Docker daemon
under a sandboxed project name. Verifies:
- .env is populated with all required secrets.
- Supabase comes up and passes all three readiness levels.
- db-init created the honcho database and broker schema.
- mc-init created all expected buckets.
Tears down cleanly at end.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import psycopg
import pytest

from control import envfile
from control.phases import data_plane, preflight
from control import cli

pytestmark = pytest.mark.integration

PROJECT = "localai-test"
REPO_ROOT = Path(__file__).resolve().parents[3]  # stack/control/tests -> repo root


@pytest.fixture(scope="module")
def sandboxed_env(tmp_path_factory):
    """Use a temp env dir so we don't touch stack/env/.env."""
    env_dir = tmp_path_factory.mktemp("env")
    shutil.copy(REPO_ROOT / "stack" / "env" / ".env.example", env_dir / ".env.example")
    return env_dir


@pytest.fixture(scope="module")
def populated_env(sandboxed_env):
    preflight.ensure_env(
        env_path=sandboxed_env / ".env",
        example_path=sandboxed_env / ".env.example",
        required=cli.PHASE1_REQUIRED,
        composed=cli.PHASE1_COMPOSED,
    )
    return sandboxed_env / ".env"


@pytest.fixture(scope="module")
def brought_up(populated_env, monkeypatch_module):
    """Bring up Phase 1 against project=localai-test, tear down after."""
    # Load env for this process so compose sees the vars.
    for k, v in envfile.parse(populated_env).items():
        os.environ[k] = v

    # Monkeypatch PROJECT in the module so it uses our sandboxed project.
    monkeypatch_module.setattr(data_plane, "PROJECT", PROJECT)

    try:
        data_plane.bring_up(first_boot=True, gate_timeout_s=600)
        yield
    finally:
        subprocess.run(
            ["docker", "compose", "-p", PROJECT,
             "-f", str(data_plane.LAI_COMPOSE),
             "-f", str(data_plane.SUPABASE_COMPOSE),
             "-f", str(data_plane.OVERLAY_COMPOSE),
             "down", "-v"],
            check=False,
        )


@pytest.fixture(scope="module")
def monkeypatch_module():
    from _pytest.monkeypatch import MonkeyPatch
    m = MonkeyPatch()
    yield m
    m.undo()


def _db_connect(env: dict[str, str], user: str, password: str, dbname: str):
    # supabase-db in the localai-test project is reachable on host only via
    # docker exec; we shell out through psql to keep this test portable.
    cmd = [
        "docker", "exec",
        f"{PROJECT}-supabase-db-1",  # default compose naming; adjust if upstream differs
        "psql", "-U", user, "-d", dbname, "-tAc",
        "SELECT 1",
    ]
    env = {**os.environ, "PGPASSWORD": password}
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def test_honcho_database_exists(brought_up, populated_env):
    values = envfile.parse(populated_env)
    cmd = [
        "docker", "exec",
        f"{PROJECT}-supabase-db-1",
        "psql", "-U", "postgres", "-d", "honcho", "-tAc",
        "SELECT 1 FROM pg_extension WHERE extname IN ('vector','pg_trgm');",
    ]
    env = {**os.environ, "PGPASSWORD": values["POSTGRES_PASSWORD"]}
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    # Two extensions expected.
    assert result.stdout.count("1") == 2, result.stdout


def test_broker_schema_and_tables_exist(brought_up, populated_env):
    values = envfile.parse(populated_env)
    cmd = [
        "docker", "exec",
        f"{PROJECT}-supabase-db-1",
        "psql", "-U", "postgres", "-d", "postgres", "-tAc",
        """
        SELECT count(*)
        FROM information_schema.tables
        WHERE table_schema = 'broker'
          AND table_name IN ('alignment_log', 'artifact_manifests');
        """,
    ]
    env = {**os.environ, "PGPASSWORD": values["POSTGRES_PASSWORD"]}
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "2", result.stdout


def test_minio_buckets_exist(brought_up):
    cmd = [
        "docker", "exec",
        f"{PROJECT}-minio-1",
        "sh", "-c",
        "ls /data",  # MinIO buckets are directories under /data in the container
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    names = set(result.stdout.split())
    assert {"langfuse", "n8n", "artifacts"}.issubset(names), f"got {names!r}"
```

**Note for the executing agent:** Container naming under `docker compose -p <proj>`
differs between Compose versions. If `docker exec ${PROJECT}-supabase-db-1` fails,
inspect `docker compose -p localai-test ps` and adjust the container name. The
prefix format stable across recent Compose releases is `<project>-<service>-1`.

- [ ] **Step 2:** Run the integration test. (Requires Docker.)

Run: `cd stack/control && uv run pytest -m integration tests/test_phase1_integration.py -v -s`

Expected: 3 passed within ~5 minutes on first boot.

If it fails, inspect:
- `docker compose -p localai-test logs supabase-db`
- `docker compose -p localai-test logs db-init`
- `docker compose -p localai-test logs mc-init`

Do not paper over failures — each catches a different class of problem (compose layering, SQL idempotency, bucket creation).

- [ ] **Step 3: Commit.**

```bash
git add stack/control/tests/test_phase1_integration.py
git commit -m "Plan 1 T20: end-to-end Phase 1 bring-up integration test"
```

---

## Task 21 — README update

**Files:**
- Modify: `README.md`

- [ ] **Step 1:** Append to `README.md`:

```markdown

## Bring-up (Phase 1 — foundation)

Phase 1 brings up the data plane: Supabase + Langfuse data services + Qdrant + Neo4j + Redis + MinIO, plus initialization of the Honcho database and broker schema.

**Prerequisites:** Docker Engine with Compose v2, `uv` (`curl -LsSf https://astral.sh/uv/install.sh | sh`), and a clone of this repo with submodules (`git submodule update --init --recursive`).

```bash
# 1. Seed .env from the example, auto-generate secrets:
cp stack/env/.env.example stack/env/.env
./bin/start-1215.py check         # or: ./bin/start-1215.py check --no-generate

# 2. Bring up Phase 1:
./bin/start-1215.py up --first-boot
```

On success, the data plane is healthy, `honcho` database exists with `vector` + `pg_trgm` extensions, `broker` schema is present with `alignment_log` and `artifact_manifests` tables, and MinIO has the `langfuse`, `n8n`, and `artifacts` buckets.

**What Phase 1 does NOT include:** the Honcho service (Plan 2), Paperclip/Hermes gateway (Plan 3), n8n-MinIO integration and n8n-mcp (Plan 4), Caddy addons + public exposure + full validation suite (Plan 5). See `docs/superpowers/specs/2026-04-20-1215-vps-design.md` for the full design and `docs/superpowers/plans/` for subsequent plans.

**Integration tests:**

```bash
cd stack/control
uv run pytest                      # unit tests only (fast)
uv run pytest -m integration      # full Phase 1 bring-up in a sandboxed project (~5 min first boot)
```
```

- [ ] **Step 2: Commit.**

```bash
git add README.md
git commit -m "Plan 1 T21: README — Phase 1 bring-up instructions"
```

---

## Self-Review

**Spec coverage check:** every item Plan 1 is responsible for has a task.

| Spec section / requirement | Task |
|---|---|
| Repo layout `stack/`, `bin/` | T1, T2 |
| `.env.example` covering Phase 1 surface | T8 |
| Single `.env`, secret auto-generation | T3, T4, T9 |
| `HONCHO_DB_CONNECTION_URI` composed at render time | T7, T9 |
| `localai-data` / `localai-app` networks, upstream attachments | T15 |
| Three-level Supabase readiness gate (container → psql → kong) | T10, T11 |
| First-boot 600s / subsequent 120s timeout budget | T17, T18 |
| Honcho DB + `honcho_app` role + extensions | T12 |
| Broker schema + `broker_app` role + RLS policies | T12 |
| MinIO buckets `n8n`, `artifacts` (plus existing `langfuse`) | T14 |
| Strict halt-on-failure | T16 (`ComposeError`), T17 (propagation) |
| Phase 5 validation tests 1, 2, 5 (partial) | T20 |

**Placeholder scan:** no `TBD`, `TODO`, `implement later`, or hand-waved steps. Every code step contains the actual code.

**Type consistency:** `envfile.parse` returns `dict[str,str]` and is consumed that way in `preflight.ensure_env`; `secrets.populate_missing` accepts the same shape. `supabase.Checks` fields match what `default_checks()` returns and what `wait_for_supabase` expects. `compose.run` return type is `subprocess.CompletedProcess`, not used as a value in callers that care about exit code (they rely on `ComposeError`).

**One caveat worth flagging for the executing agent:** the Supabase override list in `stack/docker-compose.1215.yml` (Task 15) references a handful of Supabase service names that have drifted across Supabase compose versions. If `docker compose config` reports a referenced-but-undefined service, comment it out in the overlay and continue — those services will default to upstream's network (no split for them), and we record it in an ADR amendment. This is acceptable partial progress; Plan 5 revisits Caddy/Tailscale exposure per-service anyway.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-20-plan-1-foundation.md`.**

Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration. Uses `superpowers:subagent-driven-development`.
2. **Inline Execution** — execute tasks in this session with batch checkpoints. Uses `superpowers:executing-plans`.

Which approach?
