# =============================================================================
# AI Civilization Simulator — Cross-Cloud Dockerfile
#
# Works identically on:
#   - Azure Container Apps  (injects PORT env var)
#   - Google Cloud Run      (injects PORT env var)
#   - AWS Lambda            (Lambda Web Adapter translates Lambda events → HTTP)
#
# The AWS Lambda Web Adapter binary is copied in at build time.
# On ACA and Cloud Run, /opt/extensions/ is simply ignored by the runtime.
# The CMD is the same on every platform — no code changes needed per cloud.
# =============================================================================

# --- Stage 1: Python dependency builder ---
FROM python:3.13-slim AS deps

WORKDIR /deps

# Install dependencies into an isolated venv so they can be copied cleanly.
COPY backend/pyproject.toml .
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir \
      "fastapi>=0.115.0" \
      "uvicorn[standard]>=0.32.0" \
      "sqlalchemy>=2.0.36" \
      "alembic>=1.14.0" \
      "asyncpg>=0.30.0" \
      "pydantic>=2.10.0" \
      "pydantic-settings>=2.6.0" \
      "openai>=1.0.0" \
      "python-dotenv>=1.0.0" \
      "greenlet>=3.1.1"

# --- Stage 2: Runtime image ---
FROM python:3.13-slim

# AWS Lambda Web Adapter — transparent HTTP bridge for Lambda container images.
# Listens on AWS_LWA_PORT, forwards Lambda invocations as plain HTTP requests.
# On Cloud Run / ACA this directory is unused — zero overhead.
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.8.4 \
     /lambda-adapter /opt/extensions/lambda-adapter

WORKDIR /app

# Venv from builder stage
COPY --from=deps /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Application source
COPY backend/app       ./app
COPY backend/alembic   ./alembic
COPY backend/alembic.ini .
COPY backend/seed      ./seed

# ---- Runtime environment ----
# PORT   — the port uvicorn binds to.
#          Cloud Run and ACA set this automatically; default 8000.
# AWS_LWA_PORT — must match PORT so the Lambda Web Adapter forwards correctly.
# PYTHONUNBUFFERED — stream logs immediately (important for cloud log tailing).
ENV PORT=8000 \
    AWS_LWA_PORT=8000 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production

EXPOSE $PORT

# Single CMD — works on ACA, Cloud Run, and Lambda (via LWA).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
