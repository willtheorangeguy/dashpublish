# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1: build the React (Vite) SPA.
# ---------------------------------------------------------------------------
FROM node:20-alpine AS frontend

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: python runtime.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# ffmpeg is required by the compile/render pipeline; git is required for
# `uv tool install git+...` (sentrysearch).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini

# The built SPA must land inside src/dashpublish/web *before* the package is
# installed below, so hatchling packages the static assets into the wheel.
# dashpublish.api.app._resolve_web_dir() prefers src/dashpublish/web over
# frontend/dist for exactly this reason.
COPY --from=frontend /frontend/dist ./src/dashpublish/web

RUN uv pip install --system --no-cache .

# sentrysearch is an *optional* external CLI (semantic video search over
# ChromaDB). Its install can fail here (network hiccup, upstream changes,
# etc.) without breaking this image: dashpublish falls back to
# DASHPUBLISH_FAKE=1 for an offline demo, or sentrysearch can be installed
# manually inside a running container later.
ENV PATH="/root/.local/bin:${PATH}"
RUN uv tool install "git+https://github.com/ssrajadh/sentrysearch" \
    || echo "sentrysearch install failed; install manually or use fake mode"

ENV DASHPUBLISH_CONFIG=/app/dashpublish.toml

ENTRYPOINT ["dashpublish"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
