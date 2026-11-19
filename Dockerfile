# syntax=docker/dockerfile:1.4
# Multi-stage production Dockerfile for Pura Stone Mineral Skincare ERP & Financial Command Center

FROM python:3.12-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install --no-install-recommends -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --user --no-warn-script-location -r requirements.txt && \
    pip install --user --no-warn-script-location gunicorn psycopg2-binary

# Final runtime image
FROM python:3.12-slim AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/home/purastone/.local/bin:$PATH"

RUN apt-get update && apt-get install --no-install-recommends -y \
    libpq5 \
    curl \
    openssl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Run as non-privileged user for DevSecOps hardening
RUN groupadd -g 1001 purastone && \
    useradd -u 1001 -g purastone -m -s /bin/bash purastone

COPY --from=builder --chown=purastone:purastone /root/.local /home/purastone/.local
COPY --chown=purastone:purastone . /app

# Create static and media directories with proper permissions
RUN mkdir -p /app/static /app/media && \
    chown -R purastone:purastone /app/static /app/media

USER purastone

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/healthz || exit 1

CMD ["gunicorn", "ims_core.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4", "--threads", "2", "--timeout", "60", "--access-logfile", "-", "--error-logfile", "-"]
