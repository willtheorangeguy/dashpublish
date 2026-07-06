"""CLI tests: init/index/scan/clips/compile/publish/jobs, driven via CliRunner.

All tests run in fake mode (``DASHPUBLISH_FAKE=1``) against a tmp config + data
directory so nothing touches the real ``~/.dashpublish``, the network, or YouTube.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from dashpublish.cli._common import ensure_db
from dashpublish.cli.main import app
from dashpublish.config import load_config, reset_config
from dashpublish.db import repo
from dashpublish.db.engine import session_scope
from dashpublish.jobs import queue, tasks
from dashpublish.paths import resolve_paths
from dashpublish.testing import make_category, make_clip, make_video

runner = CliRunner()


@pytest.fixture()
def ctx(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    footage_dir = tmp_path / "footage"
    footage_dir.mkdir()
    cfg_path = tmp_path / "dashpublish.toml"
    cfg_path.write_text(
        f'[general]\nfootage_dir = "{footage_dir.as_posix()}"\n'
        f'data_dir = "{data_dir.as_posix()}"\n'
    )
    monkeypatch.setenv("DASHPUBLISH_FAKE", "1")
    monkeypatch.setenv("DASHPUBLISH_NO_WORKER", "1")
    monkeypatch.setenv("DASHPUBLISH_CONFIG", str(cfg_path))
    reset_config()
    cfg = load_config()
    paths = resolve_paths(cfg)
    yield SimpleNamespace(
        cfg=cfg,
        cfg_path=cfg_path,
        db_path=str(paths.db_path),
        tmp=tmp_path,
        footage_dir=footage_dir,
        data_dir=data_dir,
    )
    reset_config()


def _seed_starred_clip(ctx, score: float = 0.9) -> int:
    ensure_db(load_config())
    clip_file = ctx.tmp / "clip1.mp4"
    clip_file.write_bytes(b"clip-bytes")
    with session_scope(ctx.db_path) as session:
        video = make_video(session, path=str(ctx.tmp / "vid1.mp4"))
        cat = make_category(session, name="overtake-x")
        clip = make_clip(
            session,
            video_id=video.id,
            category_id=cat.id,
            clip_path=str(clip_file),
            start_s=0.0,
            end_s=8.0,
            score=score,
            starred=True,
        )
        return clip.id


def _rendered_compilation_id(ctx, monkeypatch) -> int:
    """Seed a starred clip and run ``compile`` with rendering monkeypatched."""
    _seed_starred_clip(ctx)
    from dashpublish.compile.render import RenderResult

    def fake_render(edl, clips, profile, output_path, **kw):
        cb = kw.get("progress_cb")
        if cb:
            cb(1.0)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"fake-render")
        return RenderResult(output_path=str(output_path), duration_s=8.0)

    monkeypatch.setattr(tasks, "render", fake_render)
    result = runner.invoke(app, ["compile", "--profile", "short", "--from", "starred"])
    assert result.exit_code == 0, result.output
    with session_scope(ctx.db_path) as session:
        return repo.list_compilations(session)[0].id


# =========================================================================
# init
# =========================================================================


def test_init_creates_toml_db_and_categories(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DASHPUBLISH_CONFIG", raising=False)
    monkeypatch.setenv("DASHPUBLISH_FAKE", "1")
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("USERPROFILE", str(home_dir))
    reset_config()

    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "dashpublish.toml").exists()
    assert "Database ready" in result.output

    cfg = load_config()
    paths = resolve_paths(cfg)
    assert str(paths.data_dir).startswith(str(home_dir))
    assert paths.db_path.exists()
    with session_scope(str(paths.db_path)) as session:
        cats = repo.list_categories(session)
    assert len(cats) >= 8
    reset_config()


def test_init_leaves_existing_config_unchanged(ctx):
    original = ctx.cfg_path.read_text(encoding="utf-8")
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output
    assert "leaving it unchanged" in result.output
    assert ctx.cfg_path.read_text(encoding="utf-8") == original


# =========================================================================
# index
# =========================================================================


def test_index_registers_footage_tree(ctx):
    (ctx.footage_dir / "a.mp4").write_bytes(b"a")
    (ctx.footage_dir / "b.mp4").write_bytes(b"b")

    result = runner.invoke(app, ["index"])
    assert result.exit_code == 0, result.output
    assert "2 new" in result.output
    assert "Indexed 2 video(s)" in result.output

    with session_scope(ctx.db_path) as session:
        assert len(repo.list_videos(session)) == 2


def test_index_explicit_path_overrides_config(ctx):
    other_dir = ctx.tmp / "other_footage"
    other_dir.mkdir()
    (other_dir / "c.mp4").write_bytes(b"c")

    result = runner.invoke(app, ["index", str(other_dir)])
    assert result.exit_code == 0, result.output
    assert "1 new" in result.output

    with session_scope(ctx.db_path) as session:
        videos = repo.list_videos(session)
    assert len(videos) == 1
    assert "other_footage" in videos[0].path


# =========================================================================
# scan
# =========================================================================


def test_scan_dry_run_prints_and_leaves_real_db_untouched(ctx):
    result = runner.invoke(app, ["scan", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "[dry-run]" in result.output
    assert "categories_run=8" in result.output
    # The real database was never created for a dry run.
    assert not Path(ctx.db_path).exists()


def test_scan_unknown_category_exits_1(ctx):
    result = runner.invoke(app, ["scan", "--category", "does-not-exist"])
    assert result.exit_code == 1
    assert "Unknown category" in result.output


def test_scan_real_seeds_categories_and_runs(ctx):
    result = runner.invoke(app, ["scan"])
    assert result.exit_code == 0, result.output
    assert "categories_run=8" in result.output
    assert Path(ctx.db_path).exists()
    with session_scope(ctx.db_path) as session:
        assert len(repo.list_scans(session)) == 1


# =========================================================================
# clips
# =========================================================================


def test_clips_list_json_and_star_unstar(ctx):
    clip_id = _seed_starred_clip(ctx)

    result = runner.invoke(app, ["clips", "list", "--json"])
    assert result.exit_code == 0, result.output
    assert f'"id": {clip_id}' in result.output
    assert '"starred": true' in result.output

    result = runner.invoke(app, ["clips", "list"])
    assert result.exit_code == 0, result.output
    assert "overtake-x" in result.output

    result = runner.invoke(app, ["clips", "star", str(clip_id), "--unstar"])
    assert result.exit_code == 0, result.output
    assert "unstarred" in result.output
    with session_scope(ctx.db_path) as session:
        assert repo.get_clip(session, clip_id).starred is False

    result = runner.invoke(app, ["clips", "star", str(clip_id)])
    assert result.exit_code == 0, result.output
    assert "starred" in result.output
    with session_scope(ctx.db_path) as session:
        assert repo.get_clip(session, clip_id).starred is True


def test_clips_list_starred_only_filter(ctx):
    _seed_starred_clip(ctx)
    with session_scope(ctx.db_path) as session:
        video = make_video(session, path=str(ctx.tmp / "vid2.mp4"))
        cat = repo.get_category_by_name(session, "overtake-x")
        make_clip(session, video_id=video.id, category_id=cat.id, start_s=0.0, end_s=5.0, starred=False)

    result = runner.invoke(app, ["clips", "list", "--json"])
    assert result.output.count('"id"') == 2

    result = runner.invoke(app, ["clips", "list", "--starred", "--json"])
    assert result.output.count('"id"') == 1


def test_clips_star_unknown_id_exits_1(ctx):
    result = runner.invoke(app, ["clips", "star", "999"])
    assert result.exit_code == 1
    assert "not found" in result.output


# =========================================================================
# compile
# =========================================================================


def test_compile_invalid_profile_exits_1(ctx):
    result = runner.invoke(app, ["compile", "--profile", "bogus"])
    assert result.exit_code == 1
    assert "--profile" in result.output


def test_compile_plan_only_prints_edl(ctx):
    clip_id = _seed_starred_clip(ctx)
    result = runner.invoke(
        app, ["compile", "--profile", "short", "--from", "starred", "--plan-only"]
    )
    assert result.exit_code == 0, result.output
    assert '"segments"' in result.output
    assert f'"clip_id": {clip_id}' in result.output

    with session_scope(ctx.db_path) as session:
        comps = repo.list_compilations(session)
    assert len(comps) == 1
    assert comps[0].status == "draft"
    assert comps[0].output_path is None  # plan-only never renders


def test_compile_end_to_end_with_monkeypatched_render(ctx, monkeypatch):
    comp_id = _rendered_compilation_id(ctx, monkeypatch)
    with session_scope(ctx.db_path) as session:
        comp = repo.get_compilation(session, comp_id)
        assert comp.status == "rendered"
        assert Path(comp.output_path).exists()


def test_compile_planning_failure_is_reported(ctx):
    # ensure the schema/categories exist but seed no clips at all.
    ensure_db(load_config())
    result = runner.invoke(app, ["compile", "--profile", "short", "--from", "starred"])
    assert result.exit_code == 1
    assert "Planning failed" in result.output


# =========================================================================
# publish
# =========================================================================


def test_publish_upload_and_go_fake_mode(ctx, monkeypatch):
    comp_id = _rendered_compilation_id(ctx, monkeypatch)

    result = runner.invoke(app, ["publish", "upload", str(comp_id)])
    assert result.exit_code == 0, result.output
    assert "Uploaded: video_id=fake-yt-1" in result.output
    assert "Generated metadata" in result.output

    with session_scope(ctx.db_path) as session:
        records = repo.list_publish_records(session, compilation_id=comp_id)
    assert len(records) == 1
    record_id = records[0].id

    result = runner.invoke(app, ["publish", "go", str(record_id)])
    assert result.exit_code == 0, result.output
    assert "Published: https://youtu.be/fake-yt-1" in result.output

    with session_scope(ctx.db_path) as session:
        assert repo.get_compilation(session, comp_id).status == "published"


def test_publish_upload_explicit_metadata_skips_generation(ctx, monkeypatch):
    comp_id = _rendered_compilation_id(ctx, monkeypatch)

    result = runner.invoke(
        app,
        [
            "publish",
            "upload",
            str(comp_id),
            "--title",
            "My title",
            "--description",
            "My desc",
            "--tags",
            "a,b",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Generated metadata" not in result.output

    with session_scope(ctx.db_path) as session:
        record = repo.list_publish_records(session, compilation_id=comp_id)[0]
    assert record.title == "My title"
    assert record.tags_json == ["a", "b"]


def test_publish_upload_not_rendered_reports_error(ctx):
    ensure_db(load_config())
    with session_scope(ctx.db_path) as session:
        comp = repo.create_compilation(session, profile="short", status="draft")
        comp_id = comp.id

    result = runner.invoke(
        app,
        [
            "publish",
            "upload",
            str(comp_id),
            "--title",
            "t",
            "--description",
            "d",
            "--tags",
            "",
        ],
    )
    assert result.exit_code == 1
    assert "Upload failed" in result.output


# =========================================================================
# jobs
# =========================================================================


def test_jobs_lists_recent_jobs(ctx):
    ensure_db(load_config())
    with session_scope(ctx.db_path) as session:
        queue.enqueue(session, "scan", {})

    result = runner.invoke(app, ["jobs"])
    assert result.exit_code == 0, result.output
    assert "scan" in result.output


def test_jobs_no_jobs_message(ctx):
    result = runner.invoke(app, ["jobs"])
    assert result.exit_code == 0, result.output
    assert "No jobs." in result.output
