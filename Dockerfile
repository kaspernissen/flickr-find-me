# syntax=docker/dockerfile:1
FROM python:3.11-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev
# Bake the face models into the image so the first run needs no download.
RUN FLICKR_FIND_ME_MODELS=/models /app/.venv/bin/python -c \
    "from flickr_find_me.faces import FaceEngine; FaceEngine()" \
    && rm -f /models/models/*.zip && chmod -R a+rX /models

FROM python:3.11-slim
COPY --from=build /app /app
COPY --from=build /models /models
ENV PATH=/app/.venv/bin:$PATH \
    FLICKR_FIND_ME_MODELS=/models \
    HOME=/tmp \
    PYTHONWARNINGS=ignore::FutureWarning
WORKDIR /work
ENTRYPOINT ["flickr-find-me"]
