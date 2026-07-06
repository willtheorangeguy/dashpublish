"""Shared API dependencies: config overlay, DB path, and per-request helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Request

from dashpublish.config import Config, load_config
from dashpublish.db import repo
from dashpublish.db.engine import session_scope

# Settings-table keys that override config at read time, mapped to the
# (section, field) they overlay onto a :class:`~dashpublish.config.Config`.
SETTINGS_OVERLAY: dict[str, tuple[str, str]] = {
    "footage_dir": ("general", "footage_dir"),
    "embeddings_backend": ("embeddings", "backend"),
    "llm_provider": ("llm", "provider"),
    "llm_model": ("llm", "model"),
    "ollama_url": ("llm", "ollama_url"),
}


def effective_config(db_path: str | Path, base_cfg: Config | None = None) -> Config:
    """Overlay runtime settings-table values onto the loaded config.

    The five UI-editable keys in :data:`SETTINGS_OVERLAY` win over the TOML/env
    config; secrets and ``fake_mode`` are preserved from the base config. Used by
    the job tasks and the ``/settings`` route so the UI's edits take effect without
    a restart.
    """
    cfg = base_cfg if base_cfg is not None else load_config()
    with session_scope(db_path) as session:
        overrides = {s.key: s.value for s in repo.list_settings(session)}

    relevant = {k: v for k, v in overrides.items() if k in SETTINGS_OVERLAY and v is not None}
    if not relevant:
        return cfg

    data: dict[str, Any] = cfg.model_dump()
    for key, value in relevant.items():
        section, field = SETTINGS_OVERLAY[key]
        data[section][field] = value
    return Config.model_validate(data)


# --- request-scoped accessors (state set in create_app) -------------------


def get_base_config(request: Request) -> Config:
    return request.app.state.cfg


def get_db_path(request: Request) -> str:
    return request.app.state.db_path


def get_paths(request: Request):
    return request.app.state.paths


def get_effective_config(request: Request) -> Config:
    return effective_config(request.app.state.db_path, request.app.state.cfg)
