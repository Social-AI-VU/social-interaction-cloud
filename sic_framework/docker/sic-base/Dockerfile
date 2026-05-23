FROM python:3.11-slim-bookworm AS base

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        procps \
        gcc \
        python3-dev \
        portaudio19-dev \
        libturbojpeg0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# PyPI installs: build context is unused; sic_compose sets target=pypi.
FROM base AS pypi
ARG SIC_VERSION=2.2.3
RUN pip install --no-cache-dir "social-interaction-cloud==${SIC_VERSION}"

# Source checkout: build context is the repo root; sic_compose sets target=local.
FROM base AS local
COPY . /tmp/social-interaction-cloud
RUN pip install --no-cache-dir "/tmp/social-interaction-cloud" \
    && rm -rf /tmp/social-interaction-cloud
