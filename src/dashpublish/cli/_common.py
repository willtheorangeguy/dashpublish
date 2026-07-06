"""Shared helpers for CLI commands: config/db bootstrap and sentry client selection.

Every command is expected to call :func:`ensure_db` before touching the database so
that a bare ``dashpublish index`` (without an explicit ``dashpublish init`` first)
still works against a freshly migrated, seeded database.
"""

from __future__ import annotations

from dashpublish.config import Config, load_config
from dashpublish.db import repo
from dashpublish.db.engine import session_scope, upgrade_db
from dashpublish.paths import Paths, resolve_paths
from dashpublish.sentry import FakeSentryClient, SentrySearchClient


def get_cfg() -> Config:
    """Return the current (cached) configuration."""
    return load_config()


def ensure_db(cfg: Config) -> tuple[str, Paths]:
    """Migrate the database to head and seed the built-in categories.

    Idempotent: safe to call on every command invocation. Returns
    ``(db_path, paths)``.
    """
    paths = resolve_paths(cfg)
    db_path = str(paths.db_path)
    upgrade_db(db_path)
    with session_scope(db_path) as session:
        repo.seed_default_categories(session)
    return db_path, paths


def make_sentry_client(cfg: Config) -> FakeSentryClient | SentrySearchClient:
    """Return a fake client in fake mode, otherwise the real sentrysearch client."""
    if cfg.fake_mode:
        return FakeSentryClient()
    return SentrySearchClient(backend=cfg.embeddings.backend)
