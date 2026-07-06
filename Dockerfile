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

# Alembic migration scripts ship inside the package (src/dashpublish/migrations),
# so no separate COPY is needed for them.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

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
# SENTRYSEARCH_EXTRAS selects optional sentrysearch backends, e.g.
#   docker compose build --build-arg SENTRYSEARCH_EXTRAS=local
# for the offline Qwen3-VL backend ([embeddings].backend = "local"). Note the
# local extra downloads a multi-GB model on first index and wants a GPU or
# plenty of RAM. Default is the slim install (gemini/dashscope API backends).
ARG SENTRYSEARCH_EXTRAS=""
RUN if [ -n "$SENTRYSEARCH_EXTRAS" ]; then \
        SPEC="sentrysearch[$SENTRYSEARCH_EXTRAS] @ git+https://github.com/ssrajadh/sentrysearch"; \
    else \
        SPEC="git+https://github.com/ssrajadh/sentrysearch"; \
    fi \
    && uv tool install "$SPEC" \
    || echo "sentrysearch install failed; install manually or use fake mode"

ENV DASHPUBLISH_CONFIG=/app/dashpublish.toml

ENTRYPOINT ["dashpublish"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
