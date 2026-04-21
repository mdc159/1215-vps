#!/usr/bin/env python3
"""Functional test for required prototype-local n8n-mcp behavior."""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from urllib import error, request

from common import REPO_ROOT, parse_env, require_command, wait_for_http


WORKFLOW_DIR = REPO_ROOT / "stack" / "prototype-local" / "n8n"
N8N_BASE_URL = "http://127.0.0.1:5678"
N8N_MCP_URL = "http://127.0.0.1:13000/mcp"


def is_placeholder(value: str) -> bool:
    return value.strip().startswith("replace-with-")


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
        "label": f"prototype-local-functional-{uuid.uuid4().hex[:8]}",
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
    auth_token: str,
    n8n_api_key: str,
    n8n_url: str,
    session_id: str | None = None,
    expected_status: int = 200,
) -> tuple[dict[str, object], dict[str, str]]:
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "x-n8n-url": n8n_url,
        "x-n8n-key": n8n_api_key,
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
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
                raise SystemExit(f"unexpected n8n-mcp HTTP status {response.status} for {payload.get('method')}")
            response_headers = {key: value for key, value in response.headers.items()}
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise SystemExit(f"n8n-mcp request failed ({exc.code}) for {payload.get('method')}: {detail}") from exc
    parsed = None
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        parsed = None
    if not isinstance(parsed, dict):
        for line in body.splitlines():
            if not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if not raw:
                continue
            try:
                candidate = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                parsed = candidate
        if not isinstance(parsed, dict):
            raise SystemExit(f"invalid JSON from n8n-mcp for {payload.get('method')}")
    return parsed, response_headers


def initialize_mcp_session(auth_token: str, n8n_api_key: str, n8n_url: str) -> str:
    _, headers = mcp_request(
        {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "prototype-local-functional", "version": "1.0.0"},
            },
            "id": "functional-init",
        },
        auth_token=auth_token,
        n8n_api_key=n8n_api_key,
        n8n_url=n8n_url,
    )
    session_id = headers.get("Mcp-Session-Id") or headers.get("mcp-session-id")
    if not session_id:
        raise SystemExit("initialize did not return Mcp-Session-Id")
    return session_id


def call_tool(
    name: str,
    arguments: dict[str, object],
    *,
    auth_token: str,
    n8n_api_key: str,
    n8n_url: str,
    session_id: str,
) -> dict[str, object]:
    response, _ = mcp_request(
        {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
            "id": f"tool-{name}-{uuid.uuid4().hex[:8]}",
        },
        auth_token=auth_token,
        n8n_api_key=n8n_api_key,
        n8n_url=n8n_url,
        session_id=session_id,
    )
    if "error" in response:
        raise SystemExit(f"mcp tool call failed for {name}: {response['error']}")
    return response


def parse_tool_content_objects(response: dict[str, object]) -> list[dict[str, object]]:
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


def assert_no_embedded_failure(response: dict[str, object], tool_name: str) -> None:
    for obj in parse_tool_content_objects(response):
        if obj.get("success") is False:
            raise SystemExit(f"{tool_name} reported failure: {obj}")
        data = obj.get("data")
        if isinstance(data, dict) and data.get("success") is False:
            raise SystemExit(f"{tool_name} reported failure: {data}")


def extract_workflows(response: dict[str, object]) -> list[dict[str, object]]:
    for obj in parse_tool_content_objects(response):
        workflows = obj.get("workflows")
        if isinstance(workflows, list):
            return [item for item in workflows if isinstance(item, dict)]
        data = obj.get("data")
        if isinstance(data, dict):
            nested = data.get("workflows")
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
    return []


def extract_workflow_id(response: dict[str, object]) -> str | None:
    for obj in parse_tool_content_objects(response):
        for container in (obj, obj.get("data")):
            if isinstance(container, dict):
                value = container.get("id")
                if isinstance(value, str) and value:
                    return value
    return None


def response_has_nodes(response: dict[str, object]) -> bool:
    for obj in parse_tool_content_objects(response):
        for container in (obj, obj.get("data")):
            if isinstance(container, dict):
                nodes = container.get("nodes")
                if isinstance(nodes, list) and nodes:
                    return True
    return False


def expect_real_token(name: str, value: str) -> str:
    token = value.strip()
    if not token:
        raise SystemExit(f"{name} is blank in stack/prototype-local/.env")
    if token.startswith("replace-with-"):
        raise SystemExit(f"{name} is still placeholder text in stack/prototype-local/.env")
    return token


def expected_imported_workflow_names() -> set[str]:
    names: set[str] = set()
    for source in WORKFLOW_DIR.glob("*.json"):
        if source.name.endswith(".manifest.json"):
            continue
        payload = json.loads(source.read_text())
        name = payload.get("name")
        if isinstance(name, str) and name:
            names.add(name)
    return names


def validate_negative_missing_node_repair(
    auth_token: str,
    n8n_api_key: str,
    n8n_url: str,
    session_id: str,
) -> None:
    broken_name = f"Prototype Missing Node Negative {uuid.uuid4().hex[:8]}"
    broken_workflow = {
        "name": broken_name,
        "nodes": [
            {
                "id": "manual_1",
                "name": "Manual Trigger",
                "type": "n8n-nodes-base.manualTrigger",
                "typeVersion": 1,
                "position": [240, 280],
                "parameters": {},
            },
            {
                "id": "missing_1",
                "name": "Missing Runtime Node",
                "type": "n8n-nodes-base.thisNodeDoesNotExist",
                "typeVersion": 1,
                "position": [520, 280],
                "parameters": {},
            },
        ],
        "connections": {
            "Manual Trigger": {"main": [[{"node": "Missing Runtime Node", "type": "main", "index": 0}]]}
        },
    }
    validation_response = call_tool(
        "validate_workflow",
        {"workflow": broken_workflow},
        auth_token=auth_token,
        n8n_api_key=n8n_api_key,
        n8n_url=n8n_url,
        session_id=session_id,
    )
    validation_dump = json.dumps(validation_response).lower()
    if '"valid": true' in validation_dump:
        raise SystemExit("negative test failed: broken workflow unexpectedly validated as valid")
    if "doesnotexist" not in validation_dump and "missing runtime node" not in validation_dump:
        raise SystemExit("negative test failed: missing runtime node was not surfaced in validation output")

    create_response = call_tool(
        "n8n_create_workflow",
        broken_workflow,
        auth_token=auth_token,
        n8n_api_key=n8n_api_key,
        n8n_url=n8n_url,
        session_id=session_id,
    )
    created_id = extract_workflow_id(create_response)
    if not created_id:
        if "error" in json.dumps(create_response).lower():
            return
        raise SystemExit("negative test failed: broken workflow create returned neither error nor workflow id")

    try:
        fetched = call_tool(
            "n8n_get_workflow",
            {"id": created_id, "mode": "structure"},
            auth_token=auth_token,
            n8n_api_key=n8n_api_key,
            n8n_url=n8n_url,
            session_id=session_id,
        )
        fetched_dump = json.dumps(fetched).lower()
        # Negative repair assertion: invalid node type must not be silently repaired.
        if "thisnodedoesnotexist" not in fetched_dump and "missing runtime node" not in fetched_dump:
            raise SystemExit("negative test failed: broken node was silently repaired during create")
    finally:
        call_tool(
            "n8n_delete_workflow",
            {"id": created_id},
            auth_token=auth_token,
            n8n_api_key=n8n_api_key,
            n8n_url=n8n_url,
            session_id=session_id,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-limit", type=int, default=100, help="Max workflows to request from n8n-mcp.")
    args = parser.parse_args()

    require_command("docker")
    env = parse_env()
    auth_token = expect_real_token("N8N_MCP_AUTH_TOKEN", env.get("N8N_MCP_AUTH_TOKEN", ""))
    effective_n8n_api_key = resolve_effective_n8n_api_key(env)
    effective_mcp_n8n_url = resolve_effective_mcp_n8n_url(env)

    wait_for_http(f"{N8N_BASE_URL}/healthz/readiness")
    wait_for_http("http://127.0.0.1:13000/health")

    session_id = initialize_mcp_session(auth_token, effective_n8n_api_key, effective_mcp_n8n_url)

    tools_response, _ = mcp_request(
        {"jsonrpc": "2.0", "method": "tools/list", "id": "functional-tools"},
        auth_token=auth_token,
        n8n_api_key=effective_n8n_api_key,
        n8n_url=effective_mcp_n8n_url,
        session_id=session_id,
    )
    result = tools_response.get("result")
    if not isinstance(result, dict):
        raise SystemExit("tools/list missing result payload")
    tools = result.get("tools")
    if not isinstance(tools, list):
        raise SystemExit("tools/list missing tools array")
    tool_names = {str(item.get("name")) for item in tools if isinstance(item, dict) and "name" in item}

    required_tools = {
        "search_nodes",
        "n8n_list_workflows",
        "n8n_get_workflow",
        "n8n_create_workflow",
        "n8n_delete_workflow",
        "validate_workflow",
        "n8n_health_check",
    }
    missing = sorted(required_tools - tool_names)
    if missing:
        raise SystemExit(f"n8n-mcp is missing required tools for prototype functional tests: {', '.join(missing)}")

    health_response = call_tool(
        "n8n_health_check",
        {},
        auth_token=auth_token,
        n8n_api_key=effective_n8n_api_key,
        n8n_url=effective_mcp_n8n_url,
        session_id=session_id,
    )
    assert_no_embedded_failure(health_response, "n8n_health_check")
    if "error" in health_response:
        raise SystemExit(f"n8n_health_check reported error: {health_response['error']}")

    node_search_response = call_tool(
        "search_nodes",
        {"query": "webhook", "limit": 5, "source": "core"},
        auth_token=auth_token,
        n8n_api_key=effective_n8n_api_key,
        n8n_url=effective_mcp_n8n_url,
        session_id=session_id,
    )
    assert_no_embedded_failure(node_search_response, "search_nodes")
    node_dump = json.dumps(node_search_response).lower()
    if "webhook" not in node_dump:
        raise SystemExit("search_nodes did not return expected webhook-related node results")

    list_response = call_tool(
        "n8n_list_workflows",
        {"limit": args.list_limit},
        auth_token=auth_token,
        n8n_api_key=effective_n8n_api_key,
        n8n_url=effective_mcp_n8n_url,
        session_id=session_id,
    )
    assert_no_embedded_failure(list_response, "n8n_list_workflows")
    workflows = extract_workflows(list_response)
    if not workflows:
        raise SystemExit("n8n_list_workflows returned no workflow records")

    expected_names = expected_imported_workflow_names()
    matching = [wf for wf in workflows if isinstance(wf.get("name"), str) and wf["name"] in expected_names]
    if not matching:
        raise SystemExit("n8n-mcp workflow listing did not include any repo-imported prototype workflows")

    target_workflow = matching[0]
    workflow_id = target_workflow.get("id")
    if not isinstance(workflow_id, str) or not workflow_id:
        raise SystemExit("unable to locate workflow id for inspection test")

    structure_response = call_tool(
        "n8n_get_workflow",
        {"id": workflow_id, "mode": "structure"},
        auth_token=auth_token,
        n8n_api_key=effective_n8n_api_key,
        n8n_url=effective_mcp_n8n_url,
        session_id=session_id,
    )
    assert_no_embedded_failure(structure_response, "n8n_get_workflow")
    if not response_has_nodes(structure_response):
        fallback_response = call_tool(
            "n8n_get_workflow",
            {"id": workflow_id},
            auth_token=auth_token,
            n8n_api_key=effective_n8n_api_key,
            n8n_url=effective_mcp_n8n_url,
            session_id=session_id,
        )
        assert_no_embedded_failure(fallback_response, "n8n_get_workflow")
        if not response_has_nodes(fallback_response):
            raise SystemExit("n8n_get_workflow response did not include node metadata")

    disposable_name = f"Prototype MCP Disposable {uuid.uuid4().hex[:8]}"
    disposable_payload = {
        "name": disposable_name,
        "nodes": [
            {
                "id": "manual_1",
                "name": "Manual Trigger",
                "type": "n8n-nodes-base.manualTrigger",
                "typeVersion": 1,
                "position": [280, 320],
                "parameters": {},
            },
            {
                "id": "set_1",
                "name": "Set",
                "type": "n8n-nodes-base.set",
                "typeVersion": 3.4,
                "position": [540, 320],
                "parameters": {},
            },
        ],
        "connections": {
            "Manual Trigger": {"main": [[{"node": "Set", "type": "main", "index": 0}]]},
        },
    }
    create_response = call_tool(
        "n8n_create_workflow",
        disposable_payload,
        auth_token=auth_token,
        n8n_api_key=effective_n8n_api_key,
        n8n_url=effective_mcp_n8n_url,
        session_id=session_id,
    )
    assert_no_embedded_failure(create_response, "n8n_create_workflow")
    disposable_id = extract_workflow_id(create_response)
    if not disposable_id:
        raise SystemExit("n8n_create_workflow did not return a disposable workflow id")

    try:
        after_create = call_tool(
            "n8n_list_workflows",
            {"limit": args.list_limit},
            auth_token=auth_token,
            n8n_api_key=effective_n8n_api_key,
            n8n_url=effective_mcp_n8n_url,
            session_id=session_id,
        )
        assert_no_embedded_failure(after_create, "n8n_list_workflows")
        created_names = {wf.get("name") for wf in extract_workflows(after_create)}
        if disposable_name not in created_names:
            raise SystemExit("disposable workflow was not visible in n8n after n8n_create_workflow")
    finally:
        call_tool(
            "n8n_delete_workflow",
            {"id": disposable_id},
            auth_token=auth_token,
            n8n_api_key=effective_n8n_api_key,
            n8n_url=effective_mcp_n8n_url,
            session_id=session_id,
        )

    validate_negative_missing_node_repair(
        auth_token,
        effective_n8n_api_key,
        effective_mcp_n8n_url,
        session_id,
    )

    output = {
        "tools_checked": sorted(required_tools),
        "workflow_inspected": {"id": workflow_id, "name": target_workflow.get("name")},
        "disposable_workflow_id": disposable_id,
        "negative_missing_node_repair": "passed",
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
