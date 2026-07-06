"""FastAPI application factory + SPA host.

``create_app(cfg)`` wires the REST routers under ``/api``, serves the built React
SPA (static assets + history-mode fallback), and — unless ``DASHPUBLISH_NO_WORKER=1``
— starts the in-process background :class:`~dashpublish.jobs.worker.Worker` for the
app's lifetime. ``dashpublish.api.app:app`` is the module-level ASGI app for uvicorn.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from starlette.responses import FileResponse, JSONResponse
from starlette.staticfiles import StaticFiles

from dashpublish.config import Config, load_config
from dashpublish.db import repo
from dashpublish.db.engine import session_scope, upgrade_db
from dashpublish.jobs.worker import Worker
from dashpublish.logging import get_logger
from dashpublish.paths import resolve_paths

from dashpublish.api.routers import (
    categories,
    clips,
    compilations,
    jobs,
    publish,
    scans,
    settings,
    videos,
)

logger = get_logger(__name__)

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]  # src/dashpublish
_PROJECT_ROOT = Path(__file__).resolve().parents[3]  # repo root


def _resolve_web_dir() -> Path | None:
    """Prefer the bundled SPA (src/dashpublish/web), fall back to frontend/dist."""
    bundled = _PACKAGE_ROOT / "web"
    if (bundled / "index.html").exists():
        return bundled
    dist = _PROJECT_ROOT / "frontend" / "dist"
    if (dist / "index.html").exists():
        return dist
    return None


def _ensure_schema(db_path: str) -> None:
    """Bring the schema to head (Alembic) and seed the built-in categories."""
    upgrade_db(db_path)
    with session_scope(db_path) as session:
        repo.seed_default_categories(session)


def _mount_spa(app: FastAPI, web_dir: Path) -> None:
    assets_dir = web_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    index_file = web_dir / "index.html"

    @app.get("/favicon.svg", include_in_schema=False)
    def favicon():  # pragma: no cover - trivial static file
        favicon_file = web_dir / "favicon.svg"
        if favicon_file.exists():
            return FileResponse(favicon_file)
        return JSONResponse({"detail": "Not found"}, status_code=404)

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        # Never let the catch-all answer for API routes.
        if full_path.startswith("api"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        candidate = web_dir / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index_file)


def create_app(cfg: Config | None = None) -> FastAPI:
    cfg = cfg if cfg is not None else load_config()
    paths = resolve_paths(cfg)
    db_path = str(paths.db_path)
    _ensure_schema(db_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        worker: Worker | None = None
        if os.environ.get("DASHPUBLISH_NO_WORKER") != "1":
            worker = Worker(db_path).start()
        try:
            yield
        finally:
            if worker is not None:
                worker.stop()

    app = FastAPI(title="dashpublish", version="1.0.0", lifespan=lifespan)
    app.state.cfg = cfg
    app.state.db_path = db_path
    app.state.paths = paths

    for module in (
        videos,
        clips,
        categories,
        scans,
        compilations,
        publish,
        jobs,
        settings,
    ):
        app.include_router(module.router, prefix="/api")

    web_dir = _resolve_web_dir()
    if web_dir is not None:
        _mount_spa(app, web_dir)
    else:
        logger.warning("no built SPA found (src/dashpublish/web or frontend/dist); serving API only")

    return app


def __getattr__(name: str):
    """Lazily build the module-level ``app`` for uvicorn (``dashpublish.api.app:app``).

    Deferring creation keeps ``from dashpublish.api.app import create_app`` free of
    side effects (no data dir / DB touched at import), which matters for tests that
    supply their own tmp config.
    """
    if name == "app":
        return create_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
