-- Broker schema inside the default `postgres` database (per ADR-016).
-- Uses PostgREST's auto-discovery: any schema named in `PGRST_DB_SCHEMAS`
-- (configured in supabase's .env) is exposed via /rest/v1/<schema>.
-- We don't modify PGRST_DB_SCHEMAS here; tables are named with a `broker_`
-- prefix and created in the `public` schema-equivalent naming convention
-- so they're visible at /rest/v1/broker_* without reconfiguring Supabase.
-- ACTUALLY: we create a dedicated `broker` schema and expose via schema naming
-- below. Supabase exposes `public`, `graphql_public`, and `storage` by default;
-- `broker` is added here.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'broker_app') THEN
        EXECUTE format(
            'CREATE ROLE broker_app LOGIN PASSWORD %L',
            current_setting('vps.broker_password')
        );
    ELSE
        EXECUTE format(
            'ALTER ROLE broker_app WITH LOGIN PASSWORD %L',
            current_setting('vps.broker_password')
        );
    END IF;
END
$$;

CREATE SCHEMA IF NOT EXISTS broker AUTHORIZATION broker_app;

-- Grant the Supabase `anon` and `authenticated` roles the ability to see
-- the schema (PostgREST expects this). Writes are still gated by RLS.
GRANT USAGE ON SCHEMA broker TO anon, authenticated, service_role, broker_app;
