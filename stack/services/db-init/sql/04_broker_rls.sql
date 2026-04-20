-- RLS policies for broker tables.
-- Strategy: writes require a valid JWT with a `peer_id` claim; reads are
-- open to anyone with a valid JWT (the broker is a shared log by design).
-- service_role bypasses RLS per Supabase convention.

SET search_path TO broker;

ALTER TABLE alignment_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE artifact_manifests ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS alignment_log_select ON alignment_log;
CREATE POLICY alignment_log_select ON alignment_log
    FOR SELECT
    TO authenticated
    USING (true);

DROP POLICY IF EXISTS artifact_manifests_select ON artifact_manifests;
CREATE POLICY artifact_manifests_select ON artifact_manifests
    FOR SELECT
    TO authenticated
    USING (true);

DROP POLICY IF EXISTS alignment_log_insert ON alignment_log;
CREATE POLICY alignment_log_insert ON alignment_log
    FOR INSERT
    TO authenticated
    WITH CHECK (peer_id = current_setting('request.jwt.claims', true)::jsonb->>'peer_id');

DROP POLICY IF EXISTS artifact_manifests_insert ON artifact_manifests;
CREATE POLICY artifact_manifests_insert ON artifact_manifests
    FOR INSERT
    TO authenticated
    WITH CHECK (peer_id = current_setting('request.jwt.claims', true)::jsonb->>'peer_id');
