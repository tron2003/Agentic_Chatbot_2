# Production Dockerfile for Agentic Chatbot
# Multi-stage build: optimized for size and security

# Stage 1: Backend Builder
FROM python:3.12-slim as backend-builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: Frontend Builder
FROM node:20-alpine as frontend-builder

WORKDIR /app/frontend

# Copy frontend files
COPY frontend/package*.json ./
RUN npm ci --legacy-peer-deps

COPY frontend .
RUN npm run build

# Stage 3: Runtime
FROM python:3.12-slim

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependencies from builder
COPY --from=backend-builder /root/.local /root/.local

# Set Python path
ENV PATH=/root/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8001 \
    SERVER_HOST=0.0.0.0

# Copy application code
COPY backend_api.py .
COPY run.py .
COPY chat_history.py .
COPY ingest.py .
COPY src/ ./src/
COPY config/ ./config/
COPY artifacts/ ./artifacts/

# Copy built frontend
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Create necessary directories
RUN mkdir -p artifacts/logs workspace/uploads config && \
    chmod +x run.py

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Expose port
EXPOSE ${PORT}

# Default command - can be overridden
CMD ["python", "run.py", "--environment", "production", "--workers", "4"]
