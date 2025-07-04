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

# Copy only the metadata requirements & install them
COPY metadata/requirements.txt ./
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
    appuser

WORKDIR /app

# Copy the venv from the builder
COPY --from=builder /venv /venv

# Bring in the metadata code and shared utils
COPY metadata/metadata.py ./metadata.py
COPY pipeline_utils ./pipeline_utils

# Create directories
RUN mkdir -p /queue /metadata \
    && chown -R appuser:appgroup /queue /metadata

# Ensure we use the venv Python
ENV PATH="/venv/bin:$PATH"
ENV PYTHONPATH="/app"

USER appuser

ENTRYPOINT ["python", "metadata.py"]
