# syntax=docker/dockerfile:1

############################################
# Builder stage: install Python deps into /venv
############################################
FROM python:3.10-slim AS builder

# install build tools
RUN apt-get update \
  && apt-get install -y --no-install-recommends gcc git libasound2-dev libsndfile1-dev \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only the splitter requirements & install them
COPY splitter/requirements.txt ./
RUN python -m venv /venv \
    && /venv/bin/pip install --upgrade pip setuptools wheel \
    && /venv/bin/pip install --no-cache-dir -r requirements.txt

############################################
# Runtime stage
############################################
FROM python:3.10-slim

ARG PUID
ARG PGID

RUN groupadd --gid "${PGID}" appgroup \
    && useradd  --uid "${PUID}" --gid  appgroup \
    --home /home/appuser \
    --create-home \
    --shell /bin/bash \
    appuser \
    && apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the venv from the builder
COPY --from=builder /venv /venv

# Bring in the splitter code and shared utils
COPY splitter/splitter.py ./splitter.py
COPY pipeline_utils ./pipeline_utils

# Create directories
RUN mkdir -p /queue /stems /app/pretrained_models \
    && chown -R appuser:appgroup /queue /stems /app/pretrained_models

# Ensure we use the venv Python
ENV PATH="/venv/bin:$PATH"
ENV PYTHONPATH="/app"

USER appuser

ENTRYPOINT ["python", "splitter.py"]
