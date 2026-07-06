"""API tests: fake-mode YouTube upload + publish, and the non-ready 409 path."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from dashpublish.api.app import create_app
from dashpublish.config import load_config, reset_config
from dashpublish.db import repo
from dashpublish.db.engine import session_scope
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


def _seed_rendered_comp(db_path, tmp, status="rendered"):
    out = tmp / "comp.mp4"
    out.write_bytes(b"\x00" * 100)
    with session_scope(db_path) as session:
        comp = repo.create_compilation(session, profile="short", status=status)
        repo.update_compilation(
            session,
            comp.id,
            output_path=str(out),
            edl_json={"segments": [{"clip_id": 1, "trim_start_s": 0, "trim_end_s": 5, "order": 0}]},
        )
        return comp.id


def test_upload_then_publish(ctx):
    comp_id = _seed_rendered_comp(ctx.db_path, ctx.tmp)

    up = ctx.client.post(
        f"/api/publish/{comp_id}/upload",
        json={"title": "Best Clips", "description": "d", "tags": ["a", "b"]},
    )
    assert up.status_code == 200
    record = up.json()
    assert record["youtube_video_id"].startswith("fake-yt-")
    assert record["tags"] == ["a", "b"]
    assert record["privacy_status"] == "private"
    # Compilation moved to uploaded.
    assert ctx.client.get(f"/api/compilations/{comp_id}").json()["status"] == "uploaded"

    listed = ctx.client.get("/api/publish").json()
    assert len(listed) == 1

    pub = ctx.client.post(f"/api/publish/{record['id']}/publish")
    assert pub.status_code == 200
    assert pub.json()["privacy_status"] == "public"
    assert pub.json()["published_at"] is not None
    assert ctx.client.get(f"/api/compilations/{comp_id}").json()["status"] == "published"


def test_upload_non_rendered_409(ctx):
    comp_id = _seed_rendered_comp(ctx.db_path, ctx.tmp, status="draft")
    res = ctx.client.post(
        f"/api/publish/{comp_id}/upload", json={"title": "x", "description": "", "tags": []}
    )
    assert res.status_code == 409


def test_upload_missing_compilation_404(ctx):
    res = ctx.client.post(
        "/api/publish/9999/upload", json={"title": "x", "description": "", "tags": []}
    )
    assert res.status_code == 404
