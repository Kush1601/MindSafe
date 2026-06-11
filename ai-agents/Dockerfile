FROM python:3.11-slim

# System deps: ffmpeg for audio/video extraction
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        fastapi "uvicorn[standard]" python-dotenv anthropic structlog \
        "fhir.resources>=8.0.0" pydantic jsonschema httpx requests \
        supabase opentelemetry-sdk opentelemetry-api \
        opentelemetry-instrumentation-fastapi \
        opentelemetry-exporter-otlp-proto-grpc \
        yt-dlp "numpy<2"

# Heavy ML deps (torch/whisper/cv2/librosa) — skip in CI, install for full pipeline
# Set INSTALL_ML_DEPS=1 to include them
ARG INSTALL_ML_DEPS=0
RUN if [ "$INSTALL_ML_DEPS" = "1" ]; then \
        pip install --no-cache-dir \
            "numpy<2" yt-dlp opencv-python librosa soundfile audioread \
            "openai-whisper" "torch<=2.2.2" "llvmlite==0.43.0" "numba==0.60.0"; \
    fi

COPY . .

EXPOSE 5001

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "5001"]
