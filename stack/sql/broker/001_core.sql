BEGIN;

CREATE SCHEMA IF NOT EXISTS broker;

CREATE TABLE IF NOT EXISTS broker.event_types (
    event_type TEXT PRIMARY KEY,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS broker.artifact_kinds (
    artifact_kind TEXT PRIMARY KEY,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS broker.checkpoint_kinds (
    checkpoint_kind TEXT PRIMARY KEY,
    description TEXT NOT NULL
);

INSERT INTO broker.event_types (event_type, description) VALUES
    ('node.upserted', 'A node registration or metadata update was recorded'),
    ('session.created', 'A new continuity session has been registered'),
    ('run.created', 'A new run has been registered'),
    ('run.started', 'A run has started execution'),
    ('run.completed', 'A run completed successfully'),
    ('run.failed', 'A run failed'),
    ('workflow.started', 'A workflow execution has started'),
    ('workflow.completed', 'A workflow execution completed'),
    ('workflow.failed', 'A workflow execution failed'),
    ('artifact.registered', 'An artifact was registered in the continuity plane'),
    ('memory.published', 'A provider published shared memory output'),
    ('memory.recalled', 'A provider surfaced shared memory recall')
ON CONFLICT (event_type) DO NOTHING;

INSERT INTO broker.artifact_kinds (artifact_kind, description) VALUES
    ('document', 'Document or note artifact'),
    ('trace-export', 'Trace or lineage export'),
    ('workflow-output', 'Workflow output payload'),
    ('memory-extract', 'Memory provider extract'),
    ('blob', 'Opaque binary or object-store artifact')
ON CONFLICT (artifact_kind) DO NOTHING;

INSERT INTO broker.checkpoint_kinds (checkpoint_kind, description) VALUES
    ('publish-outbox', 'Outbox publication cursor for a node'),
    ('replay-cursor', 'Replay cursor for shared continuity ingestion'),
    ('provider-sync', 'Memory provider synchronization checkpoint')
ON CONFLICT (checkpoint_kind) DO NOTHING;

CREATE TABLE IF NOT EXISTS broker.nodes (
    node_id TEXT PRIMARY KEY,
    node_role TEXT NOT NULL,
    display_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS broker.sessions (
    session_id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL REFERENCES broker.nodes(node_id),
    surface TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS broker.runs (
    run_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES broker.sessions(session_id),
    run_kind TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS broker.events (
    event_seq BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL REFERENCES broker.event_types(event_type),
    payload_version INTEGER NOT NULL CHECK (payload_version > 0),
    node_id TEXT NOT NULL REFERENCES broker.nodes(node_id),
    session_id TEXT REFERENCES broker.sessions(session_id),
    run_id TEXT REFERENCES broker.runs(run_id),
    idempotency_key TEXT NOT NULL,
    source_event_id TEXT REFERENCES broker.events(event_id),
    source_event_hash TEXT,
    occurred_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload_json JSONB NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT broker_events_payload_object CHECK (jsonb_typeof(payload_json) = 'object'),
    CONSTRAINT broker_events_metadata_object CHECK (jsonb_typeof(metadata_json) = 'object'),
    CONSTRAINT broker_events_source_hash_required
        CHECK (source_event_id IS NULL OR source_event_hash IS NOT NULL),
    CONSTRAINT broker_events_node_idempotency UNIQUE (node_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS broker_events_event_type_idx
    ON broker.events (event_type, occurred_at DESC);

CREATE INDEX IF NOT EXISTS broker_events_session_idx
    ON broker.events (session_id, event_seq DESC);

CREATE INDEX IF NOT EXISTS broker_events_run_idx
    ON broker.events (run_id, event_seq DESC);

CREATE TABLE IF NOT EXISTS broker.artifacts (
    artifact_id TEXT PRIMARY KEY,
    artifact_kind TEXT NOT NULL REFERENCES broker.artifact_kinds(artifact_kind),
    source_event_id TEXT NOT NULL REFERENCES broker.events(event_id),
    source_event_hash TEXT NOT NULL,
    storage_backend TEXT NOT NULL,
    uri TEXT NOT NULL,
    mime_type TEXT,
    checksum_sha256 TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT broker_artifacts_metadata_object CHECK (jsonb_typeof(metadata_json) = 'object'),
    CONSTRAINT broker_artifacts_backend_uri_unique UNIQUE (storage_backend, uri)
);

CREATE INDEX IF NOT EXISTS broker_artifacts_event_idx
    ON broker.artifacts (source_event_id, created_at DESC);

CREATE TABLE IF NOT EXISTS broker.provider_checkpoints (
    provider_name TEXT NOT NULL,
    node_id TEXT NOT NULL REFERENCES broker.nodes(node_id),
    checkpoint_kind TEXT NOT NULL REFERENCES broker.checkpoint_kinds(checkpoint_kind),
    cursor_value TEXT NOT NULL,
    source_event_id TEXT REFERENCES broker.events(event_id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT broker_provider_checkpoints_metadata_object CHECK (jsonb_typeof(metadata_json) = 'object'),
    PRIMARY KEY (provider_name, node_id, checkpoint_kind)
);

COMMIT;
