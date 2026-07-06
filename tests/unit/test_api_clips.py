"""API tests: clip listing/filtering, patching, streaming (Range), thumbnails."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from dashpublish.api import routers
from dashpublish.api.app import create_app
from dashpublish.config import load_config, reset_config
from dashpublish.db.engine import session_scope
from dashpublish.paths import resolve_paths
from dashpublish.testing import make_category, make_clip, make_video


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


def _seed_clip(db_path, clip_path=None, **clip_kw):
    with session_scope(db_path) as session:
        video = make_video(session)
        cat = make_category(session, name=f"cat-{video.id}")
        clip = make_clip(
            session,
            video_id=video.id,
            category_id=cat.id,
            clip_path=str(clip_path) if clip_path else None,
            **clip_kw,
        )
        return clip.id


def test_list_and_bool_string_filters(ctx):
    _seed_clip(ctx.db_path, score=0.9, starred=True, start_s=1.0)
    _seed_clip(ctx.db_path, score=0.4, starred=False, start_s=100.0)

    all_clips = ctx.client.get("/api/clips", params={"hidden": "false"}).json()
    assert len(all_clips) == 2
    # Response shape carries computed fields the SPA needs.
    assert {"category_name", "duration_s"} <= set(all_clips[0])

    starred = ctx.client.get("/api/clips", params={"starred": "true", "hidden": "false"}).json()
    assert len(starred) == 1
    assert starred[0]["starred"] is True

    high = ctx.client.get("/api/clips", params={"min_score": 0.5}).json()
    assert len(high) == 1 and high[0]["score"] == 0.9

    # sort=newest maps to repo "recent"; sort=score is default.
    assert ctx.client.get("/api/clips", params={"sort": "newest"}).status_code == 200


def test_patch_star(ctx):
    clip_id = _seed_clip(ctx.db_path)
    res = ctx.client.patch(f"/api/clips/{clip_id}", json={"starred": True})
    assert res.status_code == 200
    assert res.json()["starred"] is True
    assert ctx.client.patch("/api/clips/9999", json={"starred": True}).status_code == 404


def test_stream_full_and_ranges(ctx):
    data = bytes(range(256)) * 20  # 5120 bytes
    clip_file = ctx.tmp / "clip.mp4"
    clip_file.write_bytes(data)
    clip_id = _seed_clip(ctx.db_path, clip_path=clip_file)

    # Full response.
    full = ctx.client.get(f"/api/clips/{clip_id}/stream")
    assert full.status_code == 200
    assert full.headers["accept-ranges"] == "bytes"
    assert full.content == data

    # Byte range.
    part = ctx.client.get(f"/api/clips/{clip_id}/stream", headers={"Range": "bytes=0-99"})
    assert part.status_code == 206
    assert part.headers["content-range"] == f"bytes 0-99/{len(data)}"
    assert part.headers["content-length"] == "100"
    assert part.content == data[:100]

    # Suffix range.
    suffix = ctx.client.get(f"/api/clips/{clip_id}/stream", headers={"Range": "bytes=-500"})
    assert suffix.status_code == 206
    assert suffix.headers["content-range"] == f"bytes {len(data) - 500}-{len(data) - 1}/{len(data)}"
    assert suffix.content == data[-500:]

    # Unsatisfiable range.
    bad = ctx.client.get(f"/api/clips/{clip_id}/stream", headers={"Range": "bytes=99999-100000"})
    assert bad.status_code == 416


def test_stream_missing_file_404(ctx):
    clip_id = _seed_clip(ctx.db_path, clip_path=None)
    assert ctx.client.get(f"/api/clips/{clip_id}/stream").status_code == 404


def test_thumb_404_without_ffmpeg(ctx, monkeypatch):
    clip_file = ctx.tmp / "clip.mp4"
    clip_file.write_bytes(b"\x00" * 1000)
    clip_id = _seed_clip(ctx.db_path, clip_path=clip_file)
    monkeypatch.setattr(routers.clips, "resolve_ffmpeg", lambda *a, **k: None)
    assert ctx.client.get(f"/api/clips/{clip_id}/thumb").status_code == 404
