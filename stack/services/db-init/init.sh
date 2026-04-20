#!/usr/bin/env sh
# Runs SQL files in /sql/ in lexical order against the Supabase DB.
# Idempotent by construction: every SQL file uses IF NOT EXISTS / DO blocks.
#
# Env:
#   PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE — libpq standard
#   HONCHO_DB_PASSWORD — passed into psql as `vps.honcho_password` runtime setting
#   BROKER_APP_PASSWORD — passed into psql as `vps.broker_password` runtime setting

set -eu

: "${PGHOST:?PGHOST required}"
: "${PGPORT:=5432}"
: "${PGUSER:?PGUSER required}"
: "${PGPASSWORD:?PGPASSWORD required}"
: "${PGDATABASE:=postgres}"
: "${HONCHO_DB_PASSWORD:?HONCHO_DB_PASSWORD required}"
: "${BROKER_APP_PASSWORD:?BROKER_APP_PASSWORD required}"

export PGPASSWORD

echo "[db-init] waiting for postgres at ${PGHOST}:${PGPORT}..."
until pg_isready -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" >/dev/null 2>&1; do
    sleep 1
done
echo "[db-init] postgres ready"

for sql in /sql/*.sql; do
    echo "[db-init] applying $sql"
    psql \
        -v ON_ERROR_STOP=1 \
        -c "SET vps.honcho_password = '$HONCHO_DB_PASSWORD';" \
        -c "SET vps.broker_password = '$BROKER_APP_PASSWORD';" \
        -f "$sql"
done

echo "[db-init] done"
