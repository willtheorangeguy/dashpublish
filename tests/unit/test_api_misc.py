"""API tests: scans enqueue, categories CRUD, settings overlay, jobs, SPA fallback."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from dashpublish.api.app import _resolve_web_dir, create_app
from dashpublish.config import load_config, reset_config
from dashpublish.paths import resolve_paths


@pytest.fixture()
def ctx(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    cfg_path = tmp_path / "dashpublish.toml"
    cfg_path.write_text(f'[general]\ndata_dir = "{data_dir.as_posix()}"\n')
    monkeypatch.setenv("DASHPUBLISH_FAKE", "1")
    monkeypatch.setenv("DASHPUBLISH_NO_WORKER", "1")
    monkeypatch.setenv("DASHPUBLISH_CONFIG", str(cfg_path))
    reset_config()
    cfg = load_config()
    paths = resolve_paths(cfg)
    app = create_app(cfg)
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, db_path=str(paths.db_path), tmp=tmp_path)
    reset_config()


def test_scan_enqueue_returns_job(ctx):
    res = ctx.client.post("/api/scans")
    assert res.status_code == 202
    body = res.json()
    assert body["type"] == "scan" and body["status"] == "queued"
    assert ctx.client.get("/api/scans").status_code == 200


def test_categories_crud_and_builtin_delete_409(ctx):
    cats = ctx.client.get("/api/categories").json()
    assert len(cats) == 8  # seeded builtins
    builtin_id = cats[0]["id"]
    assert cats[0]["is_builtin"] is True

    created = ctx.client.post(
        "/api/categories",
        json={"name": "custom", "query_text": "a custom query", "is_builtin": False},
    )
    assert created.status_code == 201
    new_id = created.json()["id"]
    assert created.json()["is_builtin"] is False

    patched = ctx.client.patch(f"/api/categories/{new_id}", json={"threshold": 0.9})
    assert patched.status_code == 200 and patched.json()["threshold"] == 0.9

    # Deleting a custom category succeeds; a builtin is refused.
    assert ctx.client.delete(f"/api/categories/{new_id}").status_code == 204
    assert ctx.client.delete(f"/api/categories/{builtin_id}").status_code == 409


def test_settings_overlay_and_youtube_unauth(ctx):
    initial = ctx.client.get("/api/settings").json()
    assert initial["youtube_authenticated"] is False
    assert initial["llm_provider"] == "gemini"

    updated = ctx.client.put(
        "/api/settings",
        json={"footage_dir": "/mnt/footage", "llm_model": "custom-model"},
    )
    assert updated.status_code == 200
    assert updated.json()["footage_dir"] == "/mnt/footage"
    assert updated.json()["llm_model"] == "custom-model"

    # Overlay persists across a fresh GET.
    again = ctx.client.get("/api/settings").json()
    assert again["footage_dir"] == "/mnt/footage"
    assert again["llm_model"] == "custom-model"


def test_jobs_list(ctx):
    ctx.client.post("/api/scans")
    jobs = ctx.client.get("/api/jobs").json()
    assert len(jobs) == 1
    assert ctx.client.get(f"/api/jobs/{jobs[0]['id']}").status_code == 200
    assert ctx.client.get("/api/jobs/9999").status_code == 404


def test_spa_fallback(ctx):
    if _resolve_web_dir() is None:
        pytest.skip("no built SPA (frontend/dist) available")
    res = ctx.client.get("/some/client/route")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    # Unknown API paths must not be swallowed by the SPA catch-all.
    assert ctx.client.get("/api/does-not-exist").status_code == 404
