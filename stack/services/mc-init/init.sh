#!/usr/bin/env sh
# Provisions MinIO buckets idempotently.
# Uses the minio/mc image; entrypoint overridden by compose.

set -eu

: "${MINIO_ENDPOINT:=http://minio:9000}"
: "${MINIO_ROOT_USER:?MINIO_ROOT_USER required}"
: "${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD required}"

echo "[mc-init] waiting for minio at ${MINIO_ENDPOINT}..."
until /usr/bin/mc alias set local "$MINIO_ENDPOINT" "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null 2>&1; do
    sleep 1
done
echo "[mc-init] minio ready"

for bucket in langfuse n8n artifacts; do
    if /usr/bin/mc ls "local/$bucket" >/dev/null 2>&1; then
        echo "[mc-init] bucket '$bucket' already exists"
    else
        /usr/bin/mc mb "local/$bucket"
        echo "[mc-init] created bucket '$bucket'"
    fi
done

echo "[mc-init] done"
