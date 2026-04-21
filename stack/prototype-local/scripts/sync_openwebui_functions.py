#!/usr/bin/env python3
"""Bootstrap local Open WebUI admin state and sync repo-owned functions."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import uuid

import bcrypt

from common import REPO_ROOT, compose_exec, http_json, parse_env, require_command, wait_for_http


FUNCTION_DIR = REPO_ROOT / "stack" / "prototype-local" / "open-webui" / "functions"
MANIFEST_PATH = FUNCTION_DIR / "manifest.json"


def shell_quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "'\"'\"'")


def ensure_admin(env: dict[str, str]) -> str:
    email = env["OPEN_WEBUI_ADMIN_EMAIL"]
    password = env["OPEN_WEBUI_ADMIN_PASSWORD"]
    name = env["OPEN_WEBUI_ADMIN_NAME"]
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user_id = str(uuid.uuid4())

    python_snippet = f"""
import sqlite3
import time
conn = sqlite3.connect('/app/backend/data/webui.db')
cur = conn.cursor()
cur.execute("select id from user where email=?", ('{shell_quote(email)}',))
user_row = cur.fetchone()
cur.execute("select id from auth where email=?", ('{shell_quote(email)}',))
auth_row = cur.fetchone()
if user_row is None and auth_row is None:
    now = int(time.time())
    cur.execute(
        "insert into auth (id, email, password, active) values (?, ?, ?, 1)",
        ('{shell_quote(user_id)}', '{shell_quote(email)}', '{shell_quote(password_hash)}'),
    )
    cur.execute(
        \"\"\"
        insert into user (
            id, name, email, role, profile_image_url, created_at, updated_at, last_active_at
        ) values (?, ?, ?, 'admin', '', ?, ?, ?)
        \"\"\",
        ('{shell_quote(user_id)}', '{shell_quote(name)}', '{shell_quote(email)}', now, now, now),
    )
else:
    existing_id = (user_row or auth_row)[0]
    if auth_row is None:
        cur.execute(
            "insert into auth (id, email, password, active) values (?, ?, ?, 1)",
            (existing_id, '{shell_quote(email)}', '{shell_quote(password_hash)}'),
        )
    else:
        cur.execute(
            "update auth set password=?, active=1 where email=?",
            ('{shell_quote(password_hash)}', '{shell_quote(email)}'),
        )
    if user_row is None:
        now = int(time.time())
        cur.execute(
            \"\"\"
            insert into user (
                id, name, email, role, profile_image_url, created_at, updated_at, last_active_at
            ) values (?, ?, ?, 'admin', '', ?, ?, ?)
            \"\"\",
            (existing_id, '{shell_quote(name)}', '{shell_quote(email)}', now, now, now),
        )
    else:
        cur.execute(
            "update user set name=?, email=?, role='admin' where email=?",
            ('{shell_quote(name)}', '{shell_quote(email)}', '{shell_quote(email)}'),
        )
cur.execute(
    "select id from user where email=?",
    ('{shell_quote(email)}',),
)
print(cur.fetchone()[0])
conn.commit()
"""
    result = compose_exec("open-webui", ["sh", "-lc", f"python - <<'PY'\n{python_snippet}\nPY"])
    if not result.stdout.strip():
        raise SystemExit("failed to ensure Open WebUI admin state")
    return result.stdout.strip().splitlines()[-1]


def signin(env: dict[str, str]) -> str:
    response = http_json(
        "http://127.0.0.1:8080/api/v1/auths/signin",
        method="POST",
        payload={
            "email": env["OPEN_WEBUI_ADMIN_EMAIL"],
            "password": env["OPEN_WEBUI_ADMIN_PASSWORD"],
        },
    )
    if not isinstance(response, dict) or "token" not in response:
        raise SystemExit("failed to sign in to Open WebUI")
    return str(response["token"])


def extract_name(source: str) -> str:
    match = re.search(r'self\.name\s*=\s*"([^"]+)"', source)
    return match.group(1) if match else "Prototype Function"


def sync_function(entry: dict[str, object], user_id: str) -> None:
    source_path = FUNCTION_DIR / str(entry["source"])
    content = source_path.read_text()
    function_id = str(entry["id"])
    name = extract_name(content)
    meta = {
        "description": f"Repo-owned prototype function from {source_path.name}",
        "manifest": {"source": source_path.name},
    }
    valves = entry["valves"] if entry["valves"] is not None else None
    payload = {
        "id": function_id,
        "user_id": user_id,
        "name": name,
        "type": "pipe",
        "content": content,
        "meta": meta,
        "valves": valves,
        "is_active": 1 if bool(entry["active"]) else 0,
        "is_global": 0,
    }
    python_snippet = f"""
import json
import sqlite3
import time

payload = json.loads({json.dumps(json.dumps(payload))})
conn = sqlite3.connect('/app/backend/data/webui.db')
cur = conn.cursor()
now = int(time.time())
cur.execute(
    \"\"\"
    insert into function (
        id, user_id, name, type, content, meta, created_at, updated_at, valves, is_active, is_global
    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    on conflict(id) do update set
        user_id=excluded.user_id,
        name=excluded.name,
        type=excluded.type,
        content=excluded.content,
        meta=excluded.meta,
        updated_at=excluded.updated_at,
        valves=excluded.valves,
        is_active=excluded.is_active,
        is_global=excluded.is_global
    \"\"\",
    (
        payload['id'],
        payload['user_id'],
        payload['name'],
        payload['type'],
        payload['content'],
        json.dumps(payload['meta']),
        now,
        now,
        json.dumps(payload['valves']) if payload['valves'] is not None else 'null',
        payload['is_active'],
        payload['is_global'],
    ),
)
conn.commit()
"""
    compose_exec("open-webui", ["sh", "-lc", f"python - <<'PY'\n{python_snippet}\nPY"])


def purge_managed_functions(expected_ids: list[str]) -> None:
    ids_json = json.dumps(expected_ids)
    python_snippet = f"""
import json
import sqlite3

expected_ids = set(json.loads({json.dumps(ids_json)}))
conn = sqlite3.connect('/app/backend/data/webui.db')
cur = conn.cursor()
cur.execute("delete from function where id like 'prototype_%' and id not in ({','.join('?' for _ in expected_ids)})", tuple(sorted(expected_ids)))
conn.commit()
"""
    compose_exec("open-webui", ["sh", "-lc", f"python - <<'PY'\n{python_snippet}\nPY"])


def verify_models(token: str, expected_ids: list[str]) -> None:
    response = http_json(
        "http://127.0.0.1:8080/api/models",
        headers={"Authorization": f"Bearer {token}"},
    )
    if isinstance(response, dict):
        models = response.get("data", [])
    elif isinstance(response, list):
        models = response
    else:
        models = []
    model_ids = {item.get("id") for item in models if isinstance(item, dict)}
    missing = [model_id for model_id in expected_ids if model_id not in model_ids]
    if missing:
        raise SystemExit(f"missing Open WebUI models after sync: {', '.join(missing)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync repo-owned Open WebUI functions.")
    parser.parse_args()

    require_command("docker")
    env = parse_env()
    wait_for_http("http://127.0.0.1:8080/api/config")
    user_id = ensure_admin(env)
    token = signin(env)

    manifest = json.loads(MANIFEST_PATH.read_text())
    expected_ids: list[str] = []
    purge_managed_functions([str(entry["id"]) for entry in manifest["functions"]])
    for entry in manifest["functions"]:
        sync_function(entry, user_id)
        expected_ids.append(str(entry["id"]))
    verify_models(token, expected_ids)
    print("prototype-local Open WebUI functions synced")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
