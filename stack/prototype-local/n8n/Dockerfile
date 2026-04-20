FROM mwader/static-ffmpeg:7.1.1 AS ffmpeg

ARG N8N_BASE_IMAGE=n8nio/n8n:latest
FROM ${N8N_BASE_IMAGE}

USER root
COPY --from=ffmpeg /ffmpeg /usr/local/bin/ffmpeg
COPY --from=ffmpeg /ffprobe /usr/local/bin/ffprobe
USER node
