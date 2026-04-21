ARG N8N_BASE_IMAGE=n8nio/n8n:2.3.6

FROM mwader/static-ffmpeg:7.1.1 AS ffmpeg
FROM ${N8N_BASE_IMAGE}

USER root
COPY --from=ffmpeg /ffmpeg /usr/local/bin/ffmpeg
COPY --from=ffmpeg /ffprobe /usr/local/bin/ffprobe
# Keep the prototype image small and deterministic. Current repo-owned workflows
# do not depend on n8n's Python task runner, so we only add ffmpeg/ffprobe here.
USER node
