# ─────────────────────────────────────────────────────────────
# HKN POS — Multi-stage Dockerfile
# ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

WORKDIR /app

# System deps (none needed for our pure-Python stack)
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (layer cache)
COPY pyproject.toml ./
RUN pip install --no-cache-dir . \
    && pip install --no-cache-dir uvicorn

# Copy application code
COPY hkn_pos/ ./hkn_pos/

# Create directories
RUN mkdir -p /app/downloads /data

# Default env (override via docker-compose or --env-file)
ENV DB_PATH=/data/hkn_pos.db \
    DOWNLOAD_DIR=/app/downloads \
    API_PORT=8042 \
    PYTHONUNBUFFERED=1

EXPOSE 8042

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8042/health')" || exit 1

# Run the server
CMD ["python", "-m", "hkn_pos.main", "--serve"]
