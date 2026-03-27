# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — base: OS-level dependencies
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS base

# Keep Python output unbuffered for docker logs
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# System packages required by asyncpg, bcrypt, and cryptography
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        libssl3 \
        libffi8 \
        gcc \
        libpq-dev \
        libffi-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — deps: install Python packages into an isolated directory
# ─────────────────────────────────────────────────────────────────────────────
FROM base AS deps

WORKDIR /install

COPY requirements.txt .

RUN pip install --no-cache-dir --prefix=/install/packages -r requirements.txt


# ─────────────────────────────────────────────────────────────────────────────
# Stage 3 — app: final image with non-root user
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Minimal runtime libs (no gcc / dev packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        libssl3 \
        libffi8 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from deps stage
COPY --from=deps /install/packages /usr/local

# Non-root user for least-privilege execution
RUN groupadd --gid 1001 catapi \
    && useradd --uid 1001 --gid catapi --shell /bin/bash --create-home catapi

WORKDIR /app

# Copy application code
COPY app/ ./app/

# Transfer ownership so the non-root user can read the files
RUN chown -R catapi:catapi /app

USER catapi

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
