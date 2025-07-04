# syntax=docker/dockerfile:1

############################################
# Builder stage: install Python deps into /venv
############################################
FROM python:3.11-slim AS builder

# install build tools
RUN apt-get update \
  && apt-get install -y --no-install-recommends gcc git \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements & install them
COPY api/requirements.txt ./
RUN python -m venv /venv \
    && /venv/bin/pip install --upgrade pip setuptools wheel \
    && /venv/bin/pip install --no-cache-dir -r requirements.txt

############################################
# Runtime stage
############################################
FROM python:3.11-slim

ARG PUID
ARG PGID

RUN groupadd --gid "${PGID}" appgroup \
    && useradd  --uid "${PUID}" --gid  appgroup \
    --home /home/appuser \
    --create-home \
    --shell /bin/bash \
    appuser \
    && apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the venv from the builder
COPY --from=builder /venv /venv

# Bring in the API code and shared utils
COPY api/api.py ./api.py
COPY api/gunicorn.conf.py ./gunicorn.conf.py
COPY pipeline_utils ./pipeline_utils

# Create directory for input files
RUN mkdir -p /input && chown -R appuser:appgroup /input

# Ensure we use the venv Python
ENV PATH="/venv/bin:$PATH"
ENV PYTHONPATH="/app"

USER appuser

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:5000/api/health || exit 1

CMD ["gunicorn", "--config", "gunicorn.conf.py", "api:app"]
