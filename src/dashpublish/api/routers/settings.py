"""Runtime settings: GET effective values, PUT partial overrides.

The five writable keys are persisted in the ``settings`` table and overlaid on the
loaded config by :func:`dashpublish.api.deps.effective_config`. ``youtube_authenticated``
is read-only and derived from the YouTube token state (always true in fake mode).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from dashpublish.api.deps import SETTINGS_OVERLAY, effective_config, get_base_config, get_db_path
from dashpublish.api.models import SettingsApiOut, SettingsPatchIn
from dashpublish.db import repo
from dashpublish.db.engine import session_scope
from dashpublish.paths import resolve_paths
from dashpublish.youtube import is_authenticated

router = APIRouter(prefix="/settings", tags=["settings"])


def _settings_out(request: Request) -> SettingsApiOut:
    db_path = request.app.state.db_path
    cfg = effective_config(db_path, request.app.state.cfg)
    # Reflect real OAuth token presence (independent of the fake-mode upload seam).
    authenticated = is_authenticated(resolve_paths(cfg).tokens_dir)
    return SettingsApiOut(
        footage_dir=cfg.general.footage_dir,
        embeddings_backend=cfg.embeddings.backend,
        llm_provider=cfg.llm.provider,
        llm_model=cfg.llm.model,
        ollama_url=cfg.llm.ollama_url,
        youtube_authenticated=authenticated,
    )


@router.get("", response_model=SettingsApiOut)
def get_settings(request: Request) -> SettingsApiOut:
    return _settings_out(request)


@router.put("", response_model=SettingsApiOut)
def put_settings(
    patch: SettingsPatchIn,
    request: Request,
    db_path: str = Depends(get_db_path),
    _base=Depends(get_base_config),
) -> SettingsApiOut:
    updates = {k: v for k, v in patch.model_dump(exclude_unset=True).items() if v is not None}
    with session_scope(db_path) as session:
        for key, value in updates.items():
            if key in SETTINGS_OVERLAY:
                repo.set_setting(session, key, value)
    return _settings_out(request)
