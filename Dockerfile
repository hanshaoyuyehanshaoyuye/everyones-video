# Stage 1: Model pre-warm
FROM python:3.12-slim AS warmer
RUN pip install --no-cache-dir funasr==1.2.3 faster-whisper==1.2.1
RUN python3 -c "from funasr import AutoModel; AutoModel(model='paraformer-zh', disable_update=True)" 2>/dev/null || true
RUN python3 -c "from faster_whisper import WhisperModel; WhisperModel('tiny', device='cpu')" 2>/dev/null || true

# Stage 2: Runtime
FROM python:3.12-slim

LABEL org.opencontainers.image.description="Everyones Video — subtitle pipeline"
LABEL org.opencontainers.image.source="https://github.com/hanshaoyuyehanshaoyuye/everyones-video"

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg=7:7.1.2-* \
    wget \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    yt-dlp==2026.6.21 \
    funasr==1.2.3 \
    faster-whisper==1.2.1

COPY --from=warmer /root/.cache /home/pipeline/.cache

WORKDIR /app
COPY . .

RUN mkdir -p /tmp/work /app/work && chmod +x integration/pipeline.sh

RUN useradd -m pipeline 2>/dev/null || true \
    && chown -R pipeline:pipeline /app /tmp/work /app/work /home/pipeline/.cache

USER pipeline

# Secure: mount only /app and /app/work
VOLUME ["/app/work"]

ENV PIPELINE_WORK_DIR=/app/work

ENTRYPOINT ["bash", "integration/pipeline.sh"]
