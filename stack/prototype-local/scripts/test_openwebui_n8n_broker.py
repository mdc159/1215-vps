#!/usr/bin/env python3
"""Smoke test the authenticated Open WebUI -> n8n -> broker continuity path."""

from __future__ import annotations

import argparse
import json
import time
import uuid
from typing import Any

from common import compose_exec, http_json, parse_env, require_command, wait_for_http


def sql_literal(value: str) -> str:
    return value.replace("'", "''")


def psql_json(sql: str) -> dict[str, Any] | None:
    result = compose_exec(
        "postgres",
        ["psql", "-U", "postgres", "-d", "postgres", "-At", "-v", "ON_ERROR_STOP=1", "-c", sql],
    )
    payload = result.stdout.strip()
    if not payload:
        return None
    return json.loads(payload)


def signin(email: str, password: str) -> str:
    response = http_json(
        "http://127.0.0.1:8080/api/v1/auths/signin",
        method="POST",
        payload={"email": email, "password": password},
    )
    if not isinstance(response, dict) or "token" not in response:
        raise SystemExit("failed to sign in to Open WebUI")
    return str(response["token"])


def invoke_pipe(token: str, prompt: str, model: str) -> dict[str, Any]:
    response = http_json(
        "http://127.0.0.1:8080/api/chat/completions",
        method="POST",
        headers={"Authorization": f"Bearer {token}"},
        payload={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        },
    )
    if not isinstance(response, dict):
        raise SystemExit("unexpected Open WebUI completion payload")
    return response


def wait_for_event(
    prompt: str,
    timeout: int = 30,
    interval: float = 2.0,
    event_type: str | None = None,
) -> dict[str, Any]:
    deadline = time.time() + timeout
    event_type_filter = (
        f"and event_type = '{sql_literal(event_type)}'" if event_type else ""
    )
    query = f"""
select row_to_json(t)::text
from (
    select event_id, event_type, node_id, session_id, run_id, payload_json, metadata_json
    from broker.events
    where (
        payload_json->>'chat_input' = '{sql_literal(prompt)}'
        or payload_json->>'prompt' = '{sql_literal(prompt)}'
    )
    {event_type_filter}
    order by event_seq desc
    limit 1
) t;
"""
    while time.time() < deadline:
        event = psql_json(query)
        if event is not None:
            return event
        time.sleep(interval)
    raise SystemExit(f"timed out waiting for broker event for prompt {prompt!r}")


def fetch_row(table: str, key_name: str, key_value: str, fields: list[str]) -> dict[str, Any]:
    field_sql = ", ".join(fields)
    query = f"""
select row_to_json(t)::text
from (
    select {field_sql}
    from {table}
    where {key_name} = '{sql_literal(key_value)}'
) t;
"""
    row = psql_json(query)
    if row is None:
        raise SystemExit(f"missing row in {table} for {key_name}={key_value}")
    return row


def fetch_latest_artifact_event_for_run(run_id: str) -> dict[str, Any]:
    query = f"""
select row_to_json(t)::text
from (
    select event_id, event_type, node_id, session_id, run_id, payload_json, metadata_json
    from broker.events
    where run_id = '{sql_literal(run_id)}'
      and event_type = 'artifact.registered'
    order by event_seq desc
    limit 1
) t;
"""
    row = psql_json(query)
    if row is None:
        raise SystemExit(f"missing artifact.registered event for run_id={run_id}")
    return row


def fetch_artifact_by_event(event_id: str) -> dict[str, Any]:
    query = f"""
select row_to_json(t)::text
from (
    select artifact_id, artifact_kind, source_event_id, source_event_hash,
           storage_backend, uri, mime_type, checksum_sha256, metadata_json
    from broker.artifacts
    where source_event_id = '{sql_literal(event_id)}'
    order by created_at desc
    limit 1
) t;
"""
    row = psql_json(query)
    if row is None:
        raise SystemExit(f"missing broker artifact row for source_event_id={event_id}")
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Seconds to wait for broker continuity rows to appear.",
    )
    parser.add_argument(
        "--model",
        default="prototype_n8n_pipe",
        choices=("prototype_n8n_pipe", "prototype_comfyui_pipe"),
        help="Open WebUI pipe model to invoke.",
    )
    args = parser.parse_args()

    require_command("docker")
    env = parse_env()
    wait_for_http("http://127.0.0.1:8080/api/config")
    wait_for_http("http://127.0.0.1:8090/healthz")
    wait_for_http("http://127.0.0.1:5678/healthz/readiness")

    token = signin(env["OPEN_WEBUI_ADMIN_EMAIL"], env["OPEN_WEBUI_ADMIN_PASSWORD"])
    prompt_prefix = (
        "show prototype tables e2e"
        if args.model == "prototype_n8n_pipe"
        else "generate comfy prototype artifact e2e"
    )
    prompt = f"{prompt_prefix} {uuid.uuid4().hex}"
    completion = invoke_pipe(token, prompt, args.model)

    if completion.get("model") != args.model:
        raise SystemExit(f"unexpected model in completion payload: {completion!r}")
    if not isinstance(completion.get("choices"), list) or not completion["choices"]:
        raise SystemExit(f"missing completion choices: {completion!r}")

    event = wait_for_event(prompt, timeout=args.timeout, event_type="workflow.completed")
    node = fetch_row(
        "broker.nodes",
        "node_id",
        str(event["node_id"]),
        ["node_id", "node_role", "display_name", "metadata_json"],
    )
    session = fetch_row(
        "broker.sessions",
        "session_id",
        str(event["session_id"]),
        ["session_id", "node_id", "surface", "metadata_json"],
    )
    run = fetch_row(
        "broker.runs",
        "run_id",
        str(event["run_id"]),
        ["run_id", "session_id", "run_kind", "status", "metadata_json"],
    )

    if run["status"] != "completed":
        raise SystemExit(f"unexpected run status: {run['status']}")

    if args.model == "prototype_n8n_pipe":
        if node["node_id"] != "prototype-local-openwebui":
            raise SystemExit(f"unexpected node id: {node['node_id']}")
        if session["surface"] != "openwebui":
            raise SystemExit(f"unexpected session surface: {session['surface']}")
        if run["run_kind"] != "openwebui.n8n.pipe":
            raise SystemExit(f"unexpected run kind: {run['run_kind']}")
        if event["payload_json"].get("chat_input") != prompt:
            raise SystemExit("event payload chat_input does not match the test prompt")
    else:
        if node["node_id"] != "prototype-local-n8n-comfyui":
            raise SystemExit(f"unexpected node id: {node['node_id']}")
        if session["surface"] != "n8n":
            raise SystemExit(f"unexpected session surface: {session['surface']}")
        if run["run_kind"] != "n8n.prototype.comfyui.artifact":
            raise SystemExit(f"unexpected run kind: {run['run_kind']}")
        if event["payload_json"].get("prompt") != prompt:
            raise SystemExit("workflow.completed prompt does not match the test prompt")

        artifact_event = fetch_latest_artifact_event_for_run(str(run["run_id"]))
        artifact = fetch_artifact_by_event(str(artifact_event["event_id"]))

        if artifact_event["event_type"] != "artifact.registered":
            raise SystemExit(
                f"unexpected artifact event type: {artifact_event['event_type']}"
            )
        if artifact["storage_backend"] != "s3":
            raise SystemExit(
                f"unexpected artifact storage backend: {artifact['storage_backend']}"
            )
        if not str(artifact["uri"]).startswith("s3://artifacts/"):
            raise SystemExit(f"unexpected artifact uri: {artifact['uri']}")
        if not artifact.get("checksum_sha256"):
            raise SystemExit("artifact checksum_sha256 is empty")

    output = {
        "openwebui_model": completion["model"],
        "openwebui_choice_count": len(completion["choices"]),
        "completion_content": completion["choices"][0].get("message", {}).get("content", ""),
        "node_id": node["node_id"],
        "session_id": session["session_id"],
        "run_id": run["run_id"],
        "event_id": event["event_id"],
        "event_type": event["event_type"],
    }
    if args.model == "prototype_comfyui_pipe":
        artifact_event = fetch_latest_artifact_event_for_run(str(run["run_id"]))
        artifact = fetch_artifact_by_event(str(artifact_event["event_id"]))
        output["artifact_event_id"] = artifact_event["event_id"]
        output["artifact_id"] = artifact["artifact_id"]
        output["artifact_uri"] = artifact["uri"]
        output["artifact_checksum_sha256"] = artifact["checksum_sha256"]

    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
