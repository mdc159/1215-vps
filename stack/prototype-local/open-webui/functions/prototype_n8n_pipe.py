"""
title: Prototype n8n Pipe
author: OpenAI Codex
version: 0.1.0

Open WebUI pipe for the local prototype stack. It forwards the latest chat
message to an n8n webhook and converts the webhook payload into a chat reply.
"""

from __future__ import annotations

import json
import time
from typing import Awaitable, Callable, Optional

import requests
from pydantic import BaseModel, Field


def extract_event_info(event_emitter) -> tuple[Optional[str], Optional[str]]:
    if not event_emitter or not getattr(event_emitter, "__closure__", None):
        return None, None

    for cell in event_emitter.__closure__:
        if isinstance(request_info := cell.cell_contents, dict):
            chat_id = request_info.get("chat_id")
            message_id = request_info.get("message_id")
            return chat_id, message_id

    return None, None


class Pipe:
    class Valves(BaseModel):
        n8n_url: str = Field(
            default="http://n8n:5678/webhook/prototype-postgres-tables",
            description="Target n8n webhook URL.",
        )
        request_method: str = Field(
            default="POST",
            description="HTTP method used for the webhook request.",
        )
        n8n_bearer_token: str = Field(
            default="",
            description="Optional bearer token for authenticated n8n webhooks.",
        )
        input_field: str = Field(
            default="chatInput",
            description="Field name used for the latest user prompt.",
        )
        response_field: str = Field(
            default="output",
            description="Preferred field name in the n8n JSON response.",
        )
        timeout_seconds: float = Field(
            default=30.0,
            description="Webhook request timeout in seconds.",
        )
        emit_interval: float = Field(
            default=2.0, description="Interval in seconds between status emissions."
        )
        enable_status_indicator: bool = Field(
            default=True, description="Enable or disable status indicator emissions."
        )

    def __init__(self):
        self.type = "pipe"
        self.id = "prototype_n8n_pipe"
        self.name = "Prototype n8n Pipe"
        self.valves = self.Valves()
        self.last_emit_time = 0.0

    async def emit_status(
        self,
        __event_emitter__: Callable[[dict], Awaitable[None]],
        level: str,
        message: str,
        done: bool,
    ):
        current_time = time.time()
        if (
            __event_emitter__
            and self.valves.enable_status_indicator
            and (
                current_time - self.last_emit_time >= self.valves.emit_interval or done
            )
        ):
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {
                        "status": "complete" if done else "in_progress",
                        "level": level,
                        "description": message,
                        "done": done,
                    },
                }
            )
            self.last_emit_time = current_time

    def _format_payload(self, payload: object) -> str:
        if isinstance(payload, str):
            return payload

        if isinstance(payload, dict):
            preferred = payload.get(self.valves.response_field)
            if isinstance(preferred, str) and preferred.strip():
                return preferred

            names = payload.get("concatenated_table_name")
            schemas = payload.get("concatenated_table_schema")
            if isinstance(names, str) and isinstance(schemas, str):
                pairs = list(zip(schemas.split(","), names.split(",")))
                if pairs:
                    preview = ", ".join(
                        f"{schema}.{name}" for schema, name in pairs[:20]
                    )
                    remainder = len(pairs) - min(len(pairs), 20)
                    suffix = f" (+{remainder} more)" if remainder > 0 else ""
                    return f"Prototype tables: {preview}{suffix}"

            if len(payload) == 1:
                value = next(iter(payload.values()))
                if isinstance(value, str):
                    return value

            return json.dumps(payload, ensure_ascii=True)

        if isinstance(payload, list):
            return json.dumps(payload, ensure_ascii=True)

        return str(payload)

    async def pipe(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__: Callable[[dict], Awaitable[None]] = None,
        __event_call__: Callable[[dict], Awaitable[dict]] = None,
    ) -> str | dict:
        await self.emit_status(
            __event_emitter__, "info", "Calling prototype n8n workflow", False
        )

        messages = body.get("messages", [])
        if not messages:
            await self.emit_status(
                __event_emitter__, "error", "No messages found in request body", True
            )
            return "No messages found in request body"

        question = messages[-1].get("content", "")
        chat_id, message_id = extract_event_info(__event_emitter__)

        headers = {"Content-Type": "application/json"}
        if self.valves.n8n_bearer_token:
            headers["Authorization"] = f"Bearer {self.valves.n8n_bearer_token}"

        payload = {
            "sessionId": chat_id or "",
            "messageId": message_id or "",
            "userId": (__user__ or {}).get("id", ""),
        }
        payload[self.valves.input_field] = question

        try:
            method = (self.valves.request_method or "GET").upper()
            if method == "GET":
                response = requests.get(
                    self.valves.n8n_url,
                    params=payload,
                    headers=headers,
                    timeout=self.valves.timeout_seconds,
                )
            else:
                response = requests.post(
                    self.valves.n8n_url,
                    json=payload,
                    headers=headers,
                    timeout=self.valves.timeout_seconds,
                )
            response.raise_for_status()
        except Exception as exc:
            await self.emit_status(
                __event_emitter__,
                "error",
                f"n8n webhook request failed: {exc}",
                True,
            )
            return {"error": {"detail": str(exc)}}

        try:
            data = response.json()
        except ValueError:
            data = response.text

        answer = self._format_payload(data)
        await self.emit_status(__event_emitter__, "info", "Prototype webhook complete", True)
        return answer
