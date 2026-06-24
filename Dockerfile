# Stage 1: Model pre-warm (downloads models to /root/.cache)
FROM python:3.12-slim AS warmer
RUN pip install --no-cache-dir funasr>=1.2.0 faster-whisper>=1.0.0
RUN python3 -c "from funasr import AutoModel; AutoModel(model='paraformer-zh', disable_update=True)" 2>/dev/null || true
RUN python3 -c "from faster_whisper import WhisperModel; WhisperModel('tiny', device='cpu')" 2>/dev/null || true

# Stage 2: Runtime
FROM python:3.12-slim

LABEL org.opencontainers.image.description="Everyones Video — free subtitle pipeline (ASR + translate + TTS + burn)"
LABEL org.opencontainers.image.source="https://github.com/hanshaoyuyehanshaoyuye/everyones-video"

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    wget \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    yt-dlp>=2026.6.21 \
    funasr>=1.2.0 \
    faster-whisper>=1.0.0 \
    edge-tts>=6.1.0

# WhisperX (speaker diarization) — heavy (~4GB with torch+pyannote).
# Enable with build arg: docker build --build-arg WITH_WHISPERX=1 ...
# Requires HF_TOKEN env var at runtime for pyannote model access.
ARG WITH_WHISPERX=0
RUN if [ "$WITH_WHISPERX" = "1" ]; then \
    pip install --no-cache-dir whisperx>=3.1.1; \
    fi

COPY --from=warmer /root/.cache /home/pipeline/.cache

WORKDIR /app
COPY . .

RUN mkdir -p /app/work /app/tm \
    && chmod +x integration/pipeline.sh integration/batch_pipeline.sh

RUN useradd -m pipeline 2>/dev/null || true \
    && chown -R pipeline:pipeline /app /home/pipeline/.cache

USER pipeline

VOLUME ["/app/work"]
# Optional: mount TM for persistent translation memory
# docker run -v ./tm:/app/tm ... everyones-video

ENV PIPELINE_WORK_DIR=/app/work
ENV TM_PATH=/app/tm/translation_memory.json

ENTRYPOINT ["bash", "integration/pipeline.sh"]
