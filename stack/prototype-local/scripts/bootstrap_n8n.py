#!/usr/bin/env python3
"""Bootstrap prototype-local n8n owner state, credentials, workflows, and webhooks."""

from __future__ import annotations

import argparse
import json
import tempfile
import time
import uuid
from pathlib import Path
from urllib import error, request

import bcrypt

from common import REPO_ROOT, compose_cp, compose_exec, compose_restart, parse_env, require_command, wait_for_http


WORKFLOW_DIR = REPO_ROOT / "stack" / "prototype-local" / "n8n"
WORKFLOW_MANIFEST = WORKFLOW_DIR / "workflows.manifest.json"
CREDENTIAL_MANIFEST = WORKFLOW_DIR / "credentials.manifest.json"
N8N_BASE_URL = "http://127.0.0.1:5678"
N8N_MCP_URL = "http://127.0.0.1:13000/mcp"


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


def parse_mcp_content_objects(response: dict[str, object]) -> list[dict[str, object]]:
    result = response.get("result")
    if not isinstance(result, dict):
        return []
    content = result.get("content")
    if not isinstance(content, list):
        return []
    parsed: list[dict[str, object]] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if not isinstance(text, str):
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            parsed.append(payload)
    return parsed


def parse_mcp_payload(body: str, method: object) -> dict[str, object]:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        return parsed

    event_payloads: list[dict[str, object]] = []
    for line in body.splitlines():
        if not line.startswith("data:"):
            continue
        raw = line[5:].strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            event_payloads.append(payload)
    if event_payloads:
        return event_payloads[-1]
    raise SystemExit(f"invalid JSON from n8n-mcp for payload {method}")


def n8n_json_request(
    method: str,
    path: str,
    *,
    payload: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
    expected_status: int = 200,
) -> dict[str, object]:
    merged_headers = {"Accept": "application/json"}
    if headers:
        merged_headers.update(headers)
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        merged_headers["Content-Type"] = "application/json"
    req = request.Request(
        f"{N8N_BASE_URL}{path}",
        data=data,
        method=method,
        headers=merged_headers,
    )
    try:
        with request.urlopen(req, timeout=30) as response:
            body = response.read().decode("utf-8")
            if response.status != expected_status:
                raise SystemExit(f"unexpected n8n HTTP status {response.status} for {method} {path}")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise SystemExit(f"n8n request failed ({exc.code}) for {method} {path}: {detail}") from exc
    if not body:
        return {}
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON from n8n for {method} {path}") from exc
    if not isinstance(parsed, dict):
        raise SystemExit(f"unexpected JSON payload from n8n for {method} {path}")
    return parsed


def is_placeholder(value: str) -> bool:
    return value.strip().startswith("replace-with-")


def validate_n8n_api_key(api_key: str) -> bool:
    token = api_key.strip()
    if not token or is_placeholder(token):
        return False
    req = request.Request(
        f"{N8N_BASE_URL}/api/v1/workflows?limit=1",
        method="GET",
        headers={"X-N8N-API-KEY": token, "Accept": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=20) as response:
            return response.status == 200
    except error.HTTPError:
        return False


def login_owner_cookie(env: dict[str, str]) -> str:
    payload = {"emailOrLdapLoginId": env["N8N_OWNER_EMAIL"], "password": env["N8N_OWNER_PASSWORD"]}
    req = request.Request(
        f"{N8N_BASE_URL}/rest/login",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=30) as response:
            if response.status != 200:
                raise SystemExit(f"n8n owner login failed with HTTP {response.status}")
            set_cookie = response.headers.get("Set-Cookie")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise SystemExit(f"n8n owner login failed ({exc.code}): {detail}") from exc
    if not set_cookie:
        raise SystemExit("n8n owner login did not return auth cookie")
    return set_cookie.split(";", 1)[0]


def create_local_api_key(env: dict[str, str]) -> str:
    cookie = login_owner_cookie(env)
    headers = {"Cookie": cookie}
    scopes_response = n8n_json_request("GET", "/rest/api-keys/scopes", headers=headers)
    scopes = scopes_response.get("data")
    if not isinstance(scopes, list) or not scopes:
        raise SystemExit("n8n /rest/api-keys/scopes returned no scopes")
    scope_values = [scope for scope in scopes if isinstance(scope, str) and scope]
    if not scope_values:
        raise SystemExit("n8n /rest/api-keys/scopes returned invalid scope payload")
    create_payload = {
        "label": f"prototype-local-bootstrap-{uuid.uuid4().hex[:8]}",
        "expiresAt": None,
        "scopes": scope_values,
    }
    created = n8n_json_request("POST", "/rest/api-keys", payload=create_payload, headers=headers)
    created_data = created.get("data")
    if not isinstance(created_data, dict):
        raise SystemExit("n8n API key create response missing data object")
    raw_api_key = created_data.get("rawApiKey")
    if not isinstance(raw_api_key, str) or not raw_api_key.strip():
        raise SystemExit("n8n API key create response missing rawApiKey")
    return raw_api_key.strip()


def resolve_effective_n8n_api_key(env: dict[str, str]) -> str:
    configured_key = env.get("N8N_API_KEY", "").strip()
    if validate_n8n_api_key(configured_key):
        return configured_key
    generated_key = create_local_api_key(env)
    if not validate_n8n_api_key(generated_key):
        raise SystemExit("auto-generated n8n API key failed validation against /api/v1/workflows")
    return generated_key


def resolve_effective_mcp_n8n_url(env: dict[str, str]) -> str:
    configured = env.get("N8N_API_URL", "").strip()
    if configured and not is_placeholder(configured):
        return configured
    return "http://n8n:5678"


def mcp_request(
    payload: dict[str, object],
    *,
    auth_token: str | None = None,
    session_id: str | None = None,
    n8n_api_key: str | None = None,
    n8n_url: str = N8N_BASE_URL,
    expected_status: int = 200,
) -> tuple[dict[str, object], dict[str, str]]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    if n8n_api_key:
        headers["x-n8n-url"] = n8n_url
        headers["x-n8n-key"] = n8n_api_key
    req = request.Request(
        N8N_MCP_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers=headers,
    )
    try:
        with request.urlopen(req, timeout=30) as response:
            body = response.read().decode("utf-8")
            if response.status != expected_status:
                raise SystemExit(
                    f"unexpected n8n-mcp HTTP status {response.status} for payload {payload.get('method')}"
                )
            response_headers = {key: value for key, value in response.headers.items()}
    except error.HTTPError as exc:
        if exc.code != expected_status:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise SystemExit(
                f"n8n-mcp request failed ({exc.code}) for payload {payload.get('method')}: {detail}"
            ) from exc
        body = exc.read().decode("utf-8")
        response_headers = {key: value for key, value in exc.headers.items()}
    parsed = parse_mcp_payload(body, payload.get("method"))
    return parsed, response_headers


def initialize_mcp_session(auth_token: str, n8n_api_key: str, n8n_url: str) -> str:
    payload = {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "prototype-local-bootstrap", "version": "1.0.0"},
        },
        "id": "bootstrap-init",
    }
    _, headers = mcp_request(payload, auth_token=auth_token, n8n_api_key=n8n_api_key, n8n_url=n8n_url)
    session_id = headers.get("Mcp-Session-Id") or headers.get("mcp-session-id")
    if not session_id:
        raise SystemExit("n8n-mcp initialize did not return Mcp-Session-Id header")
    return session_id


def verify_n8n_mcp(env: dict[str, str]) -> None:
    wait_for_http("http://127.0.0.1:13000/health")
    auth_token = env["N8N_MCP_AUTH_TOKEN"].strip()
    if not auth_token or is_placeholder(auth_token):
        raise SystemExit("N8N_MCP_AUTH_TOKEN must be a real token in stack/prototype-local/.env")
    effective_api_key = resolve_effective_n8n_api_key(env)
    effective_mcp_n8n_url = resolve_effective_mcp_n8n_url(env)

    unauth_payload = {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "prototype-local-bootstrap-unauth", "version": "1.0.0"},
        },
        "id": "bootstrap-unauth",
    }
    try:
        mcp_request(
            unauth_payload,
            n8n_api_key=effective_api_key,
            n8n_url=effective_mcp_n8n_url,
            expected_status=401,
        )
    except SystemExit:
        mcp_request(
            unauth_payload,
            n8n_api_key=effective_api_key,
            n8n_url=effective_mcp_n8n_url,
            expected_status=403,
        )

    session_id = initialize_mcp_session(auth_token, effective_api_key, effective_mcp_n8n_url)

    tools_response, _ = mcp_request(
        {"jsonrpc": "2.0", "method": "tools/list", "id": "bootstrap-tools"},
        auth_token=auth_token,
        session_id=session_id,
        n8n_api_key=effective_api_key,
        n8n_url=effective_mcp_n8n_url,
    )
    result = tools_response.get("result")
    if not isinstance(result, dict):
        raise SystemExit("n8n-mcp tools/list missing result payload")
    tools = result.get("tools")
    if not isinstance(tools, list):
        raise SystemExit("n8n-mcp tools/list missing tools array")
    tool_names = {str(item.get("name")) for item in tools if isinstance(item, dict) and "name" in item}
    if "n8n_health_check" not in tool_names:
        raise SystemExit("n8n-mcp management tools are unavailable; expected n8n_health_check in tools/list")

    health_response, _ = mcp_request(
        {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "n8n_health_check", "arguments": {}},
            "id": "bootstrap-n8n-health",
        },
        auth_token=auth_token,
        session_id=session_id,
        n8n_api_key=effective_api_key,
        n8n_url=effective_mcp_n8n_url,
    )
    if "error" in health_response:
        raise SystemExit(f"n8n-mcp n8n_health_check failed: {health_response['error']}")
    health_objects = parse_mcp_content_objects(health_response)
    if health_objects:
        first = health_objects[0]
        if first.get("success") is False:
            raise SystemExit(f"n8n-mcp connectivity check reported failure: {first}")


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
    verify_n8n_mcp(env)
    print("prototype-local n8n bootstrap complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
