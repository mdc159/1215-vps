-- Tables owned by broker_app in the broker schema.
-- alignment_log: append-only audit of inter-company events.
-- artifact_manifests: pointer records for published artifacts (bodies in MinIO).

SET search_path TO broker;

CREATE TABLE IF NOT EXISTS alignment_log (
    log_id          bigserial PRIMARY KEY,
    occurred_at     timestamptz NOT NULL DEFAULT now(),
    peer_id         text        NOT NULL,
    event_type      text        NOT NULL,
    payload         jsonb       NOT NULL,
    prev_log_id     bigint      REFERENCES broker.alignment_log(log_id),
    content_hash    text        NOT NULL,
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
    artifact_kind   text        NOT NULL,
    title           text        NOT NULL,
    summary         text,
    storage_uri     text        NOT NULL,
    content_hash    text        NOT NULL,
    metadata        jsonb       NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT artifact_manifests_peer_hash_unique UNIQUE (peer_id, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_artifact_manifests_peer_id
    ON artifact_manifests (peer_id);
CREATE INDEX IF NOT EXISTS idx_artifact_manifests_created_at
    ON artifact_manifests (created_at);

ALTER TABLE alignment_log OWNER TO broker_app;
ALTER TABLE artifact_manifests OWNER TO broker_app;

GRANT SELECT, INSERT ON alignment_log, artifact_manifests TO authenticated, service_role;
GRANT USAGE, SELECT ON SEQUENCE alignment_log_log_id_seq TO authenticated, service_role;
