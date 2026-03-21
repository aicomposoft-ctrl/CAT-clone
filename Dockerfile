# Multi-stage Dockerfile for CAT API service
# Used as a reference/base — each service has its own Dockerfile

FROM python:3.11-slim AS base

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ─── Development stage ────────────────────────────────────────────────────────
FROM base AS development

COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ─── Production stage ─────────────────────────────────────────────────────────
FROM base AS production

COPY . .

# Non-root user for security
RUN groupadd -r catuser && useradd -r -g catuser catuser
USER catuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
