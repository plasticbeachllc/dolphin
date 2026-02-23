# syntax=docker/dockerfile:1
# Multi-stage build for Dolphin KB API server.
#
# Stage 1 (builder) — installs Python deps with uv into an isolated prefix.
# Stage 2 (runtime) — copies only the installed packages and source into a
#                     slim image, runs as a non-root user.
#
# Build:
#   docker build -t dolphin:latest .
#
# Run:
#   docker run -p 8000:8000 \
#     -e OPENAI_API_KEY=sk-... \
#     -v /host/path/to/store:/data/store \
#     dolphin:latest
#
# Health check:
#   curl http://localhost:8000/v1/health

# ── Stage 1: builder ────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Install uv (fast Python package manager)
COPY --from=ghcr.io/astral-sh/uv:0.5.26 /uv /uvx /usr/local/bin/

WORKDIR /build

# Copy dependency manifests first (layer-cached until they change)
COPY pyproject.toml uv.lock ./
COPY kb/config_template.toml kb/config_template.toml

# Install production dependencies into /build/.venv (no dev/test extras)
RUN uv sync --frozen --no-dev --no-editable

# Copy source and install the package itself
COPY kb/ kb/
RUN uv sync --frozen --no-dev --no-editable

# ── Stage 2: runtime ────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Create non-root user
RUN addgroup --system dolphin && adduser --system --ingroup dolphin dolphin

# Runtime directories — store root and config
RUN mkdir -p /data/store /etc/dolphin && \
    chown -R dolphin:dolphin /data /etc/dolphin

WORKDIR /app

# Copy the virtual environment built in stage 1
COPY --from=builder /build/.venv /app/.venv

# Activate venv by prepending to PATH
ENV PATH="/app/.venv/bin:$PATH" \
    # Tell dolphin where to write data
    DOLPHIN_STORE_ROOT="/data/store" \
    # Suppress Python bytecode writes (they are cached at build time)
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Switch to non-root user before exposing ports
USER dolphin

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/v1/health')" \
    || exit 1

# Default: start the API server
CMD ["python", "-m", "uvicorn", "kb.api.server:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--log-level", "info"]
