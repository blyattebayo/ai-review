ARG PYTHON_VERSION=3.12-slim-bullseye
FROM python:${PYTHON_VERSION}

WORKDIR /app

RUN apt-get update && \
    apt-get install -y bash ca-certificates curl git libexpat1 openssh-client && \
    rm -rf /var/lib/apt/lists/*
RUN git config --global --add safe.directory '*'
RUN git config --global core.quotepath false

COPY pyproject.toml README.md LICENSE ./
COPY ai_review ./ai_review

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .