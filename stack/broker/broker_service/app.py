from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import psycopg
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass
class BrokerConfig:
    database_conninfo: str
    database_source: str
    database_host: str | None
    database_name: str | None
    database_user: str | None
    service_name: str


def load_config() -> BrokerConfig:
    database_host = os.environ.get("BROKER_DATABASE_HOST")
    database_port = os.environ.get("BROKER_DATABASE_PORT", "5432")
    database_name = os.environ.get("BROKER_DATABASE_NAME")
    database_user = os.environ.get("BROKER_DATABASE_USER")
    database_password = os.environ.get("BROKER_DATABASE_PASSWORD")

    if any(
        value is not None
        for value in (
            database_host,
            database_name,
            database_user,
            database_password,
        )
    ):
        missing = [
            name
            for name, value in (
                ("BROKER_DATABASE_HOST", database_host),
                ("BROKER_DATABASE_NAME", database_name),
                ("BROKER_DATABASE_USER", database_user),
                ("BROKER_DATABASE_PASSWORD", database_password),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(
                "broker database configuration is incomplete; missing: "
                + ", ".join(missing)
            )

        database_conninfo = psycopg.conninfo.make_conninfo(
            host=database_host,
            port=database_port,
            dbname=database_name,
            user=database_user,
            password=database_password,
        )
        database_source = "parts"
    else:
        database_url = os.environ.get("BROKER_DATABASE_URL")
        if not database_url:
            raise RuntimeError(
                "set BROKER_DATABASE_URL or BROKER_DATABASE_HOST/"
                "BROKER_DATABASE_NAME/BROKER_DATABASE_USER/"
                "BROKER_DATABASE_PASSWORD"
            )
        database_conninfo = database_url
        database_source = "url"
        database_host = None
        database_name = None
        database_user = None

    return BrokerConfig(
        database_conninfo=database_conninfo,
        database_source=database_source,
        database_host=database_host,
        database_name=database_name,
        database_user=database_user,
        service_name=os.environ.get("BROKER_SERVICE_NAME", "broker-1215"),
    )


@contextmanager
def db_cursor():
    config = load_config()
    with psycopg.connect(config.database_conninfo) as connection:
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


class ArtifactCreate(BaseModel):
    artifact_id: str = Field(min_length=1)
    artifact_kind: str = Field(min_length=1)
    source_event_id: str = Field(min_length=1)
    source_event_hash: str = Field(min_length=1)
    storage_backend: str = Field(min_length=1)
    uri: str = Field(min_length=1)
    mime_type: str | None = None
    checksum_sha256: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CheckpointUpsert(BaseModel):
    """Provider checkpoint write.

    Shape mirrors ``broker.provider_checkpoints`` in
    ``stack/sql/broker/001_core.sql``. The primary key is
    ``(provider_name, node_id, checkpoint_kind)``; advancing the cursor
    is a plain UPSERT on ``cursor_value`` (monotonic advancement is a
    client contract, not a DB constraint — the ``broadcast_ack`` skill
    enforces it by reading-before-writing).
    """

    provider_name: str = Field(min_length=1, max_length=128)
    node_id: str = Field(min_length=1, max_length=128)
    checkpoint_kind: str = Field(min_length=1, max_length=64)
    cursor_value: str = Field(min_length=1, max_length=512)
    source_event_id: str | None = None
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
            ON CONFLICT (session_id) DO UPDATE SET
                node_id = EXCLUDED.node_id,
                surface = EXCLUDED.surface,
                metadata_json = EXCLUDED.metadata_json
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
    # Phase G: if the event belongs to a run but doesn't carry an
    # explicit Langfuse trace_id, stamp it with run_id. The gateway
    # uses run_id as trace_id so Langfuse spans + broker events share
    # one correlation key without clients having to thread it through.
    metadata = dict(event.metadata_json)
    if event.run_id and "langfuse_trace_id" not in metadata:
        metadata["langfuse_trace_id"] = event.run_id

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
                psycopg.types.json.Jsonb(metadata),
                event.node_id,
                event.idempotency_key,
            ),
        )
        row = cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=500, detail="event insert failed")

    return {"event": row}


@app.get("/events")
def list_events(
    limit: int = Query(default=50, ge=1, le=500),
    event_type: str | None = Query(default=None, min_length=1, max_length=64),
    session_id: str | None = Query(default=None, min_length=1, max_length=128),
    run_id: str | None = Query(default=None, min_length=1, max_length=128),
    node_id: str | None = Query(default=None, min_length=1, max_length=128),
    after_seq: int | None = Query(default=None, ge=0),
) -> dict[str, Any]:
    """List events, newest first, with optional filters.

    Filters are conjunctive: passing ``event_type=memory.published`` and
    ``session_id=s-1`` returns events matching both. ``after_seq`` lets
    a provider resume a feed from the last event it acknowledged
    (``broadcast_ack`` writes the cursor as ``event_seq`` in text form).
    """
    clauses: list[str] = []
    params: list[Any] = []
    if event_type is not None:
        clauses.append("event_type = %s")
        params.append(event_type)
    if session_id is not None:
        clauses.append("session_id = %s")
        params.append(session_id)
    if run_id is not None:
        clauses.append("run_id = %s")
        params.append(run_id)
    if node_id is not None:
        clauses.append("node_id = %s")
        params.append(node_id)
    if after_seq is not None:
        clauses.append("event_seq > %s")
        params.append(after_seq)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)

    with db_cursor() as cursor:
        cursor.execute(
            f"""
            SELECT event_seq, event_id, event_type, payload_version, node_id, session_id,
                   run_id, idempotency_key, source_event_id, source_event_hash,
                   occurred_at, recorded_at, payload_json, metadata_json
            FROM broker.events
            {where}
            ORDER BY event_seq DESC
            LIMIT %s
            """,
            tuple(params),
        )
        rows = cursor.fetchall()
    return {"events": rows, "count": len(rows)}


@app.post("/artifacts")
def create_artifact(artifact: ArtifactCreate) -> dict[str, Any]:
    with db_cursor() as cursor:
        cursor.execute(
            """
            WITH inserted AS (
                INSERT INTO broker.artifacts (
                    artifact_id,
                    artifact_kind,
                    source_event_id,
                    source_event_hash,
                    storage_backend,
                    uri,
                    mime_type,
                    checksum_sha256,
                    metadata_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (storage_backend, uri) DO UPDATE SET
                    artifact_kind = EXCLUDED.artifact_kind,
                    source_event_id = EXCLUDED.source_event_id,
                    source_event_hash = EXCLUDED.source_event_hash,
                    mime_type = EXCLUDED.mime_type,
                    checksum_sha256 = EXCLUDED.checksum_sha256,
                    metadata_json = EXCLUDED.metadata_json
                RETURNING artifact_id, artifact_kind, source_event_id, source_event_hash,
                          storage_backend, uri, mime_type, checksum_sha256, metadata_json, created_at
            )
            SELECT * FROM inserted
            UNION ALL
            SELECT artifact_id, artifact_kind, source_event_id, source_event_hash,
                   storage_backend, uri, mime_type, checksum_sha256, metadata_json, created_at
            FROM broker.artifacts
            WHERE storage_backend = %s AND uri = %s
            LIMIT 1
            """,
            (
                artifact.artifact_id,
                artifact.artifact_kind,
                artifact.source_event_id,
                artifact.source_event_hash,
                artifact.storage_backend,
                artifact.uri,
                artifact.mime_type,
                artifact.checksum_sha256,
                psycopg.types.json.Jsonb(artifact.metadata_json),
                artifact.storage_backend,
                artifact.uri,
            ),
        )
        row = cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=500, detail="artifact insert failed")

    return {"artifact": row}


@app.get("/artifacts")
def list_artifacts(
    source_event_id: str | None = None,
    artifact_id: str | None = Query(default=None, min_length=1, max_length=128),
    artifact_kind: str | None = Query(default=None, min_length=1, max_length=64),
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    """List artifacts, newest first, with optional filters.

    ``artifact_id`` was added in Phase F so ``artifact_read`` can look up
    a single row without scanning. All filters AND together; unset
    filters are ignored.
    """
    clauses: list[str] = []
    params: list[Any] = []
    if artifact_id is not None:
        clauses.append("artifact_id = %s")
        params.append(artifact_id)
    if source_event_id is not None:
        clauses.append("source_event_id = %s")
        params.append(source_event_id)
    if artifact_kind is not None:
        clauses.append("artifact_kind = %s")
        params.append(artifact_kind)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)

    with db_cursor() as cursor:
        cursor.execute(
            f"""
            SELECT artifact_id, artifact_kind, source_event_id, source_event_hash,
                   storage_backend, uri, mime_type, checksum_sha256, metadata_json, created_at
            FROM broker.artifacts
            {where}
            ORDER BY created_at DESC
            LIMIT %s
            """,
            tuple(params),
        )
        rows = cursor.fetchall()

    return {"artifacts": rows, "count": len(rows)}


@app.post("/checkpoints")
def upsert_checkpoint(checkpoint: CheckpointUpsert) -> dict[str, Any]:
    """Advance (or create) a provider checkpoint.

    Backs the ``broadcast_ack`` Hermes skill (Phase F). The SQL is a
    plain UPSERT — monotonic advancement is a client-side invariant
    enforced by the skill via read-before-write. The FK checks on
    ``node_id`` and ``checkpoint_kind`` will 400 the caller if either
    is unknown; callers must ``POST /nodes`` and pre-seed the kind
    (seeded by ``stack/sql/broker/001_core.sql``) first.
    """
    with db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO broker.provider_checkpoints (
                provider_name,
                node_id,
                checkpoint_kind,
                cursor_value,
                source_event_id,
                metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (provider_name, node_id, checkpoint_kind) DO UPDATE SET
                cursor_value = EXCLUDED.cursor_value,
                source_event_id = EXCLUDED.source_event_id,
                updated_at = now(),
                metadata_json = EXCLUDED.metadata_json
            RETURNING provider_name, node_id, checkpoint_kind, cursor_value,
                      source_event_id, updated_at, metadata_json
            """,
            (
                checkpoint.provider_name,
                checkpoint.node_id,
                checkpoint.checkpoint_kind,
                checkpoint.cursor_value,
                checkpoint.source_event_id,
                psycopg.types.json.Jsonb(checkpoint.metadata_json),
            ),
        )
        row = cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=500, detail="checkpoint upsert failed")

    return {"checkpoint": row}


@app.get("/checkpoints")
def list_checkpoints(
    provider_name: str | None = Query(default=None, min_length=1, max_length=128),
    node_id: str | None = Query(default=None, min_length=1, max_length=128),
    checkpoint_kind: str | None = Query(default=None, min_length=1, max_length=64),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    """List provider checkpoints with optional filters.

    With no filters this returns every row ordered by recency, which is
    useful for a "board health" glance. With all three filters set the
    response is 0 or 1 rows, suitable for an exact lookup in
    ``broadcast_ack`` (read-before-write).
    """
    clauses: list[str] = []
    params: list[Any] = []
    if provider_name is not None:
        clauses.append("provider_name = %s")
        params.append(provider_name)
    if node_id is not None:
        clauses.append("node_id = %s")
        params.append(node_id)
    if checkpoint_kind is not None:
        clauses.append("checkpoint_kind = %s")
        params.append(checkpoint_kind)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)

    with db_cursor() as cursor:
        cursor.execute(
            f"""
            SELECT provider_name, node_id, checkpoint_kind, cursor_value,
                   source_event_id, updated_at, metadata_json
            FROM broker.provider_checkpoints
            {where}
            ORDER BY updated_at DESC
            LIMIT %s
            """,
            tuple(params),
        )
        rows = cursor.fetchall()
    return {"checkpoints": rows, "count": len(rows)}


@app.get("/config")
def show_config() -> dict[str, Any]:
    config = load_config()
    return {
        "database_source": config.database_source,
        "database_host": config.database_host,
        "database_name": config.database_name,
        "database_user": config.database_user,
        "service_name": config.service_name,
    }
