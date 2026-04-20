-- Idempotent: safe to run on every bring-up.
-- Creates the honcho database and its application role.
-- Extensions are created inside the honcho database (see bottom).

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'honcho_app') THEN
        EXECUTE format(
            'CREATE ROLE honcho_app LOGIN PASSWORD %L',
            current_setting('vps.honcho_password')
        );
    ELSE
        EXECUTE format(
            'ALTER ROLE honcho_app WITH LOGIN PASSWORD %L',
            current_setting('vps.honcho_password')
        );
    END IF;
END
$$;

SELECT 'CREATE DATABASE honcho OWNER honcho_app'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'honcho')
\gexec

GRANT ALL PRIVILEGES ON DATABASE honcho TO honcho_app;

-- Extensions live inside the target DB, not `postgres`. Reconnect via \c.
\c honcho

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

GRANT ALL ON SCHEMA public TO honcho_app;
