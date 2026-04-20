from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

import psycopg
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass
class BrokerConfig:
    database_url: str
    service_name: str


def load_config() -> BrokerConfig:
    database_url = os.environ.get("BROKER_DATABASE_URL")
    if not database_url:
        raise RuntimeError("BROKER_DATABASE_URL is required")

    return BrokerConfig(
        database_url=database_url,
        service_name=os.environ.get("BROKER_SERVICE_NAME", "broker-1215"),
    )


@contextmanager
def db_cursor():
    config = load_config()
    with psycopg.connect(config.database_url) as connection:
        with connection.cursor(row_factory=psycopg.rows.dict_row) as cursor:
            yield cursor
        connection.commit()


class NodeUpsert(BaseModel):
    node_id: str = Field(min_length=1)
    node_role: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class SessionCreate(BaseModel):
    session_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    surface: str = Field(min_length=1)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class RunCreate(BaseModel):
    run_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    run_kind: str = Field(min_length=1)
    status: str = Field(min_length=1)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class EventCreate(BaseModel):
    event_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    payload_version: int = Field(ge=1)
    node_id: str = Field(min_length=1)
    session_id: str | None = None
    run_id: str | None = None
    idempotency_key: str = Field(min_length=1)
    source_event_id: str | None = None
    source_event_hash: str | None = None
    occurred_at: datetime
    payload_json: dict[str, Any]
    metadata_json: dict[str, Any] = Field(default_factory=dict)


app = FastAPI(title="1215 Broker API", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    config = load_config()
    with db_cursor() as cursor:
        cursor.execute("SELECT 1 AS ok")
        row = cursor.fetchone()

    return {
        "status": "ok",
        "service": config.service_name,
        "database": bool(row and row["ok"] == 1),
        "timestamp": utc_now().isoformat(),
    }


@app.post("/nodes")
def upsert_node(node: NodeUpsert) -> dict[str, Any]:
    with db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO broker.nodes (node_id, node_role, display_name, metadata_json)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (node_id) DO UPDATE SET
                node_role = EXCLUDED.node_role,
                display_name = EXCLUDED.display_name,
                metadata_json = EXCLUDED.metadata_json
            RETURNING node_id, node_role, display_name, metadata_json, created_at
            """,
            (
                node.node_id,
                node.node_role,
                node.display_name,
                psycopg.types.json.Jsonb(node.metadata_json),
            ),
        )
        row = cursor.fetchone()
    return {"node": row}


@app.post("/sessions")
def create_session(session: SessionCreate) -> dict[str, Any]:
    with db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO broker.sessions (session_id, node_id, surface, metadata_json)
            VALUES (%s, %s, %s, %s)
            RETURNING session_id, node_id, surface, metadata_json, created_at
            """,
            (
                session.session_id,
                session.node_id,
                session.surface,
                psycopg.types.json.Jsonb(session.metadata_json),
            ),
        )
        row = cursor.fetchone()
    return {"session": row}


@app.post("/runs")
def create_run(run: RunCreate) -> dict[str, Any]:
    with db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO broker.runs (run_id, session_id, run_kind, status, metadata_json)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (run_id) DO UPDATE SET
                status = EXCLUDED.status,
                updated_at = now(),
                metadata_json = EXCLUDED.metadata_json
            RETURNING run_id, session_id, run_kind, status, metadata_json, created_at, updated_at
            """,
            (
                run.run_id,
                run.session_id,
                run.run_kind,
                run.status,
                psycopg.types.json.Jsonb(run.metadata_json),
            ),
        )
        row = cursor.fetchone()
    return {"run": row}


@app.post("/events")
def create_event(event: EventCreate) -> dict[str, Any]:
    with db_cursor() as cursor:
        cursor.execute(
            """
            WITH inserted AS (
                INSERT INTO broker.events (
                    event_id,
                    event_type,
                    payload_version,
                    node_id,
                    session_id,
                    run_id,
                    idempotency_key,
                    source_event_id,
                    source_event_hash,
                    occurred_at,
                    payload_json,
                    metadata_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (node_id, idempotency_key) DO NOTHING
                RETURNING event_seq, event_id, event_type, payload_version, node_id, session_id,
                          run_id, idempotency_key, source_event_id, source_event_hash,
                          occurred_at, recorded_at, payload_json, metadata_json
            )
            SELECT * FROM inserted
            UNION ALL
            SELECT event_seq, event_id, event_type, payload_version, node_id, session_id,
                   run_id, idempotency_key, source_event_id, source_event_hash,
                   occurred_at, recorded_at, payload_json, metadata_json
            FROM broker.events
            WHERE node_id = %s AND idempotency_key = %s
            LIMIT 1
            """,
            (
                event.event_id,
                event.event_type,
                event.payload_version,
                event.node_id,
                event.session_id,
                event.run_id,
                event.idempotency_key,
                event.source_event_id,
                event.source_event_hash,
                event.occurred_at,
                psycopg.types.json.Jsonb(event.payload_json),
                psycopg.types.json.Jsonb(event.metadata_json),
                event.node_id,
                event.idempotency_key,
            ),
        )
        row = cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=500, detail="event insert failed")

    return {"event": row}


@app.get("/events")
def list_events(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
    with db_cursor() as cursor:
        cursor.execute(
            """
            SELECT event_seq, event_id, event_type, payload_version, node_id, session_id,
                   run_id, idempotency_key, source_event_id, source_event_hash,
                   occurred_at, recorded_at, payload_json, metadata_json
            FROM broker.events
            ORDER BY event_seq DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cursor.fetchall()
    return {"events": rows, "count": len(rows)}


@app.get("/config")
def show_config() -> dict[str, Any]:
    return asdict(load_config())
