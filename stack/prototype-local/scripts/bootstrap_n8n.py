#!/usr/bin/env python3
"""Bootstrap prototype-local n8n owner state, credentials, workflows, and webhooks."""

from __future__ import annotations

import argparse
import json
import tempfile
import time
import uuid
from pathlib import Path

import bcrypt

from common import REPO_ROOT, compose_cp, compose_exec, compose_restart, parse_env, require_command, wait_for_http


WORKFLOW_DIR = REPO_ROOT / "stack" / "prototype-local" / "n8n"
WORKFLOW_MANIFEST = WORKFLOW_DIR / "workflows.manifest.json"
CREDENTIAL_MANIFEST = WORKFLOW_DIR / "credentials.manifest.json"


def shell_quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "'\"'\"'")


def run_psql(sql: str) -> None:
    compose_exec(
        "postgres",
        ["psql", "-U", "postgres", "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-c", sql],
    )


def query_psql(sql: str) -> list[str]:
    result = compose_exec(
        "postgres",
        ["psql", "-U", "postgres", "-d", "postgres", "-At", "-v", "ON_ERROR_STOP=1", "-c", sql],
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def load_workflow_definitions() -> list[dict[str, str]]:
    workflows: list[dict[str, str]] = []
    for source in sorted(WORKFLOW_DIR.glob("*.json")):
        if source.name.endswith(".manifest.json"):
            continue
        payload = json.loads(source.read_text())
        workflows.append(
            {
                "id": str(payload["id"]),
                "name": str(payload["name"]),
                "source": source.name,
            }
        )
    return workflows


def ensure_owner_state(env: dict[str, str]) -> str:
    email = env["N8N_OWNER_EMAIL"]
    first_name = env["N8N_OWNER_FIRST_NAME"]
    last_name = env["N8N_OWNER_LAST_NAME"]
    password = env["N8N_OWNER_PASSWORD"]
    full_name = f"{first_name} {last_name}".strip()
    project_name = f"{full_name} <{email}>"
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user_id = str(uuid.uuid4())
    project_id = uuid.uuid4().hex[:16]

    sql = f"""
DO $$
DECLARE
  owner_id uuid;
  personal_project_id varchar(36);
BEGIN
  SELECT id INTO owner_id FROM "user" WHERE email = '{shell_quote(email)}';
  IF owner_id IS NULL THEN
    owner_id := '{user_id}'::uuid;
    INSERT INTO "user" (
      id, email, "firstName", "lastName", password, "roleSlug", disabled
    ) VALUES (
      owner_id,
      '{shell_quote(email)}',
      '{shell_quote(first_name)}',
      '{shell_quote(last_name)}',
      '{shell_quote(password_hash)}',
      'global:owner',
      false
    );
  ELSE
    UPDATE "user"
    SET email = '{shell_quote(email)}',
        "firstName" = '{shell_quote(first_name)}',
        "lastName" = '{shell_quote(last_name)}',
        password = '{shell_quote(password_hash)}',
        "roleSlug" = 'global:owner',
        disabled = false,
        "updatedAt" = CURRENT_TIMESTAMP
    WHERE id = owner_id;
  END IF;

  SELECT id INTO personal_project_id
  FROM project
  WHERE "creatorId" = owner_id AND type = 'personal'
  ORDER BY "createdAt"
  LIMIT 1;

  IF personal_project_id IS NULL THEN
    personal_project_id := '{project_id}';
    INSERT INTO project (id, name, type, "creatorId")
    VALUES (
      personal_project_id,
      '{shell_quote(project_name)}',
      'personal',
      owner_id
    );
  ELSE
    UPDATE project
    SET name = '{shell_quote(project_name)}',
        "creatorId" = owner_id,
        "updatedAt" = CURRENT_TIMESTAMP
    WHERE id = personal_project_id;
  END IF;

  INSERT INTO project_relation ("projectId", "userId", role)
  VALUES (personal_project_id, owner_id, 'project:personalOwner')
  ON CONFLICT ("projectId", "userId")
  DO UPDATE SET role = EXCLUDED.role, "updatedAt" = CURRENT_TIMESTAMP;

  INSERT INTO settings (key, value, "loadOnStartup")
  VALUES ('userManagement.authenticationMethod', 'email', true)
  ON CONFLICT (key)
  DO UPDATE SET value = EXCLUDED.value, "loadOnStartup" = EXCLUDED."loadOnStartup";

  INSERT INTO settings (key, value, "loadOnStartup")
  VALUES ('userManagement.isInstanceOwnerSetUp', 'true', true)
  ON CONFLICT (key)
  DO UPDATE SET value = EXCLUDED.value, "loadOnStartup" = EXCLUDED."loadOnStartup";
END $$;
"""
    run_psql(sql)
    rows = query_psql(
        f"""
select p.id
from project p
join "user" u on u.id = p."creatorId"
where u.email = '{shell_quote(email)}' and p.type = 'personal'
order by p."createdAt"
limit 1;
"""
    )
    if not rows:
        raise SystemExit(f"failed to locate personal project for {email}")
    return rows[0]


def purge_runtime_drift() -> None:
    workflow_defs = load_workflow_definitions()
    workflow_names = ", ".join(f"'{shell_quote(item['name'])}'" for item in workflow_defs)
    workflow_ids = ", ".join(f"'{shell_quote(item['id'])}'" for item in workflow_defs)
    credential_manifest = json.loads(CREDENTIAL_MANIFEST.read_text())
    credential_names = ", ".join(
        f"'{shell_quote(str(item['name']))}'" for item in credential_manifest["credentials"]
    )
    credential_ids = ", ".join(
        f"'{shell_quote(str(item['id']))}'" for item in credential_manifest["credentials"]
    )
    sql = f"""
delete from workflow_entity
where name in ({workflow_names}) or id in ({workflow_ids});

delete from credentials_entity
where name in ({credential_names}) or id in ({credential_ids});
"""
    run_psql(sql)


def render_credentials(env: dict[str, str]) -> list[dict[str, object]]:
    manifest = json.loads(CREDENTIAL_MANIFEST.read_text())
    rendered: list[dict[str, object]] = []
    for credential in manifest["credentials"]:
        data = {}
        for key, value in credential["data"].items():
            if key.endswith("_env"):
                continue
            data[key] = value
        for key, value in credential["data"].items():
            if key.endswith("_env"):
                data[key[:-4]] = env[value]
        rendered.append(
            {
                "id": credential["id"],
                "name": credential["name"],
                "type": credential["type"],
                "isManaged": False,
                "isResolvable": False,
                "isGlobal": False,
                "resolvableAllowFallback": False,
                "resolverId": None,
                "data": data,
            }
        )
    return rendered


def import_credentials(env: dict[str, str], project_id: str) -> None:
    rendered = render_credentials(env)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(rendered, handle)
        temp_path = Path(handle.name)
    remote_path = f"/tmp/prototype-credentials-{uuid.uuid4().hex}.json"
    try:
        compose_cp(temp_path, f"n8n:{remote_path}")
        compose_exec(
            "n8n",
            [
                "n8n",
                "import:credentials",
                f"--input={remote_path}",
                f"--projectId={project_id}",
            ],
        )
    finally:
        compose_exec("n8n", ["rm", "-f", remote_path], check=False)
        temp_path.unlink(missing_ok=True)


def import_workflows(project_id: str) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        for source in WORKFLOW_DIR.glob("*.json"):
            if source.name.endswith(".manifest.json"):
                continue
            target = temp_path / source.name
            target.write_text(source.read_text())
        remote_dir = f"/tmp/prototype-workflows-{uuid.uuid4().hex}"
        compose_exec("n8n", ["rm", "-rf", remote_dir], check=False)
        compose_cp(temp_path, f"n8n:{remote_dir}")
        compose_exec(
            "n8n",
            [
                "n8n",
                "import:workflow",
                "--separate",
                f"--input={remote_dir}",
                f"--projectId={project_id}",
            ],
        )
        compose_exec("n8n", ["rm", "-rf", remote_dir], check=False)


def activate_workflows() -> None:
    manifest = json.loads(WORKFLOW_MANIFEST.read_text())
    rows = query_psql("select id, name from workflow_entity order by name;")
    ids_by_name: dict[str, str] = {}
    for row in rows:
        workflow_id, name = row.split("|", 1)
        ids_by_name[name] = workflow_id
    for name in manifest["activate"]:
        workflow_id = ids_by_name[name]
        compose_exec("n8n", ["n8n", "update:workflow", f"--id={workflow_id}", "--active=true"])
    for name in manifest.get("manual_only", []):
        workflow_id = ids_by_name[name]
        compose_exec("n8n", ["n8n", "update:workflow", f"--id={workflow_id}", "--active=false"])


def restart_n8n() -> None:
    compose_restart("n8n")
    wait_for_http("http://127.0.0.1:5678/healthz/readiness")


def verify_webhooks(timeout: int = 60, interval: float = 2.0) -> None:
    expected = {
        "prototype-postgres-tables": "POST",
        "prototype-minio-buckets": "GET",
        "prototype-comfyui-system-stats": "GET",
        "prototype-comfyui-sd15": "POST",
        "prototype-comfyui-sd15-artifact": "POST",
        "prototype-media-artifact": "POST",
    }
    deadline = time.time() + timeout
    missing: list[str] = []
    while time.time() < deadline:
        result = compose_exec(
            "postgres",
            [
                "psql",
                "-U",
                "postgres",
                "-d",
                "postgres",
                "-At",
                "-c",
                'select "webhookPath" || \':\' || method from webhook_entity order by "webhookPath";',
            ],
        )
        present = set(line.strip() for line in result.stdout.splitlines() if line.strip())
        missing = [f"{path}:{method}" for path, method in expected.items() if f"{path}:{method}" not in present]
        if not missing:
            return
        time.sleep(interval)
    raise SystemExit(f"missing webhook registrations: {', '.join(missing)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap prototype-local n8n runtime state.")
    parser.parse_args()

    require_command("docker")
    env = parse_env()
    wait_for_http("http://127.0.0.1:5678/healthz/readiness")
    project_id = ensure_owner_state(env)
    purge_runtime_drift()
    import_credentials(env, project_id)
    import_workflows(project_id)
    activate_workflows()
    restart_n8n()
    verify_webhooks()
    print("prototype-local n8n bootstrap complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
