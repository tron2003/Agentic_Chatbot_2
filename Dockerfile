# One image: FastAPI serves the API and the built React UI on the same port.
#
#   docker build -t junction .
#   docker run --env-file .env -p 8001:8001 junction
#
# Build arg WITH_MCP=0 skips Node.js (smaller image, no MCP filesystem/GitHub tools).

# ── 1. Frontend build ───────────────────────────────────────────────────────
FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ── 2. Python dependencies ──────────────────────────────────────────────────
FROM python:3.12-slim AS python-deps
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY requirements.txt .
RUN pip install -r requirements.txt

# ── 3. Runtime ──────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime
ARG WITH_MCP=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl tini \
    && if [ "$WITH_MCP" = "1" ]; then apt-get install -y --no-install-recommends nodejs npm; fi \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 app
WORKDIR /app

COPY --from=python-deps /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production \
    PORT=8001 \
    WEB_CONCURRENCY=1 \
    FORWARDED_ALLOW_IPS=* \
    ENABLE_MCP=${WITH_MCP}

COPY --chown=app:app backend_api.py run.py pyproject.toml ./
COPY --chown=app:app src ./src
COPY --chown=app:app config ./config
COPY --from=frontend --chown=app:app /build/dist ./frontend/dist
RUN mkdir -p workspace/uploads && chown -R app:app workspace

USER app
EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

ENTRYPOINT ["tini", "--"]
CMD ["python", "run.py", "--env", "production"]
