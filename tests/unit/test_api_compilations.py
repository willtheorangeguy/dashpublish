"""API tests: compilation create/plan/patch(EDL normalize)/render/metadata."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from dashpublish.api.app import create_app
from dashpublish.compile.render import RenderResult
from dashpublish.config import load_config, reset_config
from dashpublish.db import repo
from dashpublish.db.engine import session_scope
from dashpublish.jobs import tasks
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


def _seed_starred_clips(db_path, tmp, n=3):
    ids = []
    with session_scope(db_path) as session:
        video = make_video(session)
        cat = make_category(session, name="overtake-x")
        for i in range(n):
            f = tmp / f"clip_{i}.mp4"
            f.write_bytes(b"\x00" * 500)
            clip = make_clip(
                session,
                video_id=video.id,
                category_id=cat.id,
                clip_path=str(f),
                start_s=float(i * 100),
                end_s=float(i * 100 + 8),
                score=0.9 - i * 0.1,
                starred=True,
            )
            ids.append(clip.id)
    return ids


def test_create_then_plan(ctx):
    _seed_starred_clips(ctx.db_path, ctx.tmp)
    created = ctx.client.post(
        "/api/compilations", json={"profile": "short", "from_selection": "starred"}
    )
    assert created.status_code == 201
    comp_id = created.json()["id"]
    # Before planning, no real EDL is exposed (candidate stash stays hidden).
    assert created.json()["edl"] is None

    plan = ctx.client.post(f"/api/compilations/{comp_id}/plan")
    assert plan.status_code == 202
    # Status flips to planning immediately.
    assert ctx.client.get(f"/api/compilations/{comp_id}").json()["status"] == "planning"

    processed = tasks.run_pending_jobs(ctx.db_path)
    assert processed == 1

    comp = ctx.client.get(f"/api/compilations/{comp_id}").json()
    assert comp["status"] == "draft"
    assert comp["edl"] is not None
    assert len(comp["edl"]["segments"]) >= 1
    # compilation_clips were resynced.
    with session_scope(ctx.db_path) as session:
        assert len(repo.list_compilation_clips(session, comp_id)) == len(comp["edl"]["segments"])


def test_patch_normalizes_frontend_segments(ctx):
    ids = _seed_starred_clips(ctx.db_path, ctx.tmp)
    comp_id = ctx.client.post(
        "/api/compilations", json={"profile": "short", "from_selection": "starred"}
    ).json()["id"]
    ctx.client.post(f"/api/compilations/{comp_id}/plan")
    tasks.run_pending_jobs(ctx.db_path)

    # Frontend editor shape: trim_start/trim_end plus stale _s keys.
    patched = ctx.client.patch(
        f"/api/compilations/{comp_id}",
        json={
            "title": "My Comp",
            "edl": {
                "segments": [
                    {
                        "clip_id": ids[0],
                        "order": 0,
                        "trim_start": 1.0,
                        "trim_end": 5.0,
                        "trim_start_s": 99.0,
                        "trim_end_s": 99.0,
                    }
                ]
            },
        },
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["title"] == "My Comp"
    seg = body["edl"]["segments"][0]
    # Canonical keys written from trim_start/trim_end; aliases dropped.
    assert seg["trim_start_s"] == 1.0 and seg["trim_end_s"] == 5.0
    assert "trim_start" not in seg and "trim_end" not in seg


def test_render_job_monkeypatched(ctx, monkeypatch):
    _seed_starred_clips(ctx.db_path, ctx.tmp)
    comp_id = ctx.client.post(
        "/api/compilations", json={"profile": "short", "from_selection": "starred"}
    ).json()["id"]
    ctx.client.post(f"/api/compilations/{comp_id}/plan")
    tasks.run_pending_jobs(ctx.db_path)

    def fake_render(edl, clips, profile, output_path, **kw):
        cb = kw.get("progress_cb")
        if cb:
            cb(1.0)
        return RenderResult(output_path=str(output_path), duration_s=12.0)

    monkeypatch.setattr(tasks, "render", fake_render)

    render_res = ctx.client.post(f"/api/compilations/{comp_id}/render")
    assert render_res.status_code == 202
    tasks.run_pending_jobs(ctx.db_path)

    comp = ctx.client.get(f"/api/compilations/{comp_id}").json()
    assert comp["status"] == "rendered"
    assert comp["output_path"].endswith(f"comp_{comp_id}.mp4")


def test_metadata_endpoint(ctx):
    _seed_starred_clips(ctx.db_path, ctx.tmp)
    comp_id = ctx.client.post(
        "/api/compilations", json={"profile": "short", "from_selection": "starred"}
    ).json()["id"]
    ctx.client.post(f"/api/compilations/{comp_id}/plan")
    tasks.run_pending_jobs(ctx.db_path)

    meta = ctx.client.post(f"/api/compilations/{comp_id}/metadata")
    assert meta.status_code == 200
    body = meta.json()
    assert body["title"] and isinstance(body["tags"], list)
    # Title persisted on the row.
    assert ctx.client.get(f"/api/compilations/{comp_id}").json()["title"] == body["title"]


def test_plan_failure_marks_failed(ctx):
    # No starred clips -> no candidates -> plan raises -> job + comp failed.
    comp_id = ctx.client.post(
        "/api/compilations", json={"profile": "short", "from_selection": "starred"}
    ).json()["id"]
    job = ctx.client.post(f"/api/compilations/{comp_id}/plan").json()
    tasks.run_pending_jobs(ctx.db_path)

    comp = ctx.client.get(f"/api/compilations/{comp_id}").json()
    assert comp["status"] == "failed"
    assert comp["error"]
    assert ctx.client.get(f"/api/jobs/{job['id']}").json()["status"] == "failed"
