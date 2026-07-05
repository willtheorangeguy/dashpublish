"""Tests for dashpublish.sentry.scan with FakeSentryClient."""

from __future__ import annotations

from pathlib import Path

import pytest

from dashpublish.config import ScanConfig
from dashpublish.db import repo
from dashpublish.db.schemas import SearchMatch
from dashpublish.sentry.client import FakeSentryClient
from dashpublish.sentry.scan import ensure_indexed, run_scan
from dashpublish.testing import make_category, make_video


def _match(**kw) -> SearchMatch:
    defaults = dict(
        score=0.8, source_file="a.mp4", start_s=10.0, end_s=15.0, saved_clip_path=None
    )
    defaults.update(kw)
    return SearchMatch(**defaults)


@pytest.fixture()
def clips_dir(tmp_path: Path) -> Path:
    d = tmp_path / "clips"
    d.mkdir()
    return d


# --- ensure_indexed -----------------------------------------------------------
def test_ensure_indexed_marks_and_counts(session):
    v1 = make_video(session, path="D:/footage/a.mp4")
    v2 = make_video(session, path="D:/footage/b.mp4")
    client = FakeSentryClient()

    count = ensure_indexed(session, client)
    assert count == 2
    assert set(client.indexed_paths) == {v1.path, v2.path}
    assert repo.get_unindexed_videos(session) == []

    # Second call: nothing left to index.
    assert ensure_indexed(session, client) == 0
    assert len(client.indexed_paths) == 2


# --- run_scan -------------------------------------------------------------------
def test_run_scan_resolves_full_path_and_basename(session, clips_dir):
    v1 = make_video(session, path="D:/footage/a.mp4")
    v2 = make_video(session, path="D:/footage/sub/b.mp4")
    cat = make_category(session, name="overtaking", query_text="overtaking query")

    client = FakeSentryClient(
        matches={
            "overtaking": [
                _match(source_file="D:/footage/a.mp4", start_s=10.0, end_s=15.0),
                _match(source_file="b.mp4", start_s=30.0, end_s=35.0, score=0.7),
                _match(source_file="unknown.mp4", start_s=50.0, end_s=55.0),
            ]
        }
    )

    result = run_scan(session, client, clips_dir, categories=[cat])
    assert result.errors == []
    assert result.categories_run == 1
    assert result.clips_found == 2  # unknown.mp4 skipped

    clips = repo.list_clips(session)
    assert {c.video_id for c in clips} == {v1.id, v2.id}
    assert all(c.scan_id == result.scan_id for c in clips)
    # Search used the category's parameters.
    assert client.searches == [
        {
            "query": "overtaking query",
            "threshold": cat.threshold,
            "save_top": cat.save_top,
            "results": 10,
            "dedupe": None,
            "rerank": cat.rerank,
        }
    ]


def test_run_scan_dedupes_across_categories_keeps_higher_score(session, clips_dir):
    v = make_video(session, path="D:/footage/a.mp4")
    cat1 = make_category(session, name="overtaking")
    cat2 = make_category(session, name="near-miss", query_text="a near miss")

    client = FakeSentryClient(
        matches={
            "overtaking": [_match(score=0.6, start_s=10.0, end_s=15.0)],
            "near miss": [_match(score=0.9, start_s=11.0, end_s=16.0)],
        }
    )

    cfg = ScanConfig(dedupe_window_s=3)
    result = run_scan(session, client, clips_dir, categories=[cat1, cat2], scan_cfg=cfg)

    clips = repo.list_clips(session)
    assert len(clips) == 1
    clip = clips[0]
    assert clip.video_id == v.id
    assert clip.score == 0.9
    assert clip.category_id == cat2.id
    assert clip.user_tags["also"] == ["overtaking"]
    assert result.clips_found == 1
    assert len(client.searches) == 2  # sequential, one per category


def test_run_scan_partial_on_category_error(session, clips_dir):
    make_video(session, path="D:/footage/a.mp4")
    cat_ok = make_category(session, name="overtaking")
    cat_bad = make_category(session, name="crash", query_text="a crash happening")

    client = FakeSentryClient(
        matches={"overtaking": [_match(score=0.8, start_s=5.0, end_s=9.0)]}
    )
    client.fail_on = {"crash"}

    result = run_scan(session, client, clips_dir, categories=[cat_ok, cat_bad])
    assert result.clips_found == 1
    assert result.categories_run == 1
    assert len(result.errors) == 1
    assert "crash" in result.errors[0]

    scans = {s.id: s for s in repo.list_scans(session)}
    row = scans[result.scan_id]
    assert row.status == "partial"
    assert "crash" in (row.error or "")
    assert row.clips_found == 1


def test_run_scan_copies_saved_clips(session, clips_dir, tmp_path):
    v = make_video(session, path="D:/footage/a.mp4")
    cat = make_category(session, name="overtaking")

    saved = tmp_path / "match_a.mp4"
    saved.write_bytes(b"clip-bytes")
    missing = tmp_path / "gone.mp4"

    client = FakeSentryClient(
        matches={
            "overtaking": [
                _match(score=0.9, start_s=10.0, end_s=15.0, saved_clip_path=str(saved)),
                _match(score=0.7, start_s=60.0, end_s=65.0, saved_clip_path=str(missing)),
                _match(score=0.6, start_s=90.0, end_s=95.0),  # no saved clip at all
            ]
        }
    )

    result = run_scan(session, client, clips_dir, categories=[cat])
    assert result.clips_found == 3

    clips = {c.start_s: c for c in repo.list_clips(session)}
    copied = clips[10.0]
    expected = clips_dir / f"clip_{v.id}_overtaking_10s.mp4"
    assert copied.clip_path == str(expected)
    assert expected.read_bytes() == b"clip-bytes"

    # Missing source file and absent saved clip both keep the row, path None.
    assert clips[60.0].clip_path is None
    assert clips[90.0].clip_path is None


def test_run_scan_uses_enabled_categories_by_default(session, clips_dir):
    make_video(session, path="D:/footage/a.mp4")
    make_category(session, name="on", query_text="query on", enabled=True)
    make_category(session, name="off", query_text="query off", enabled=False)

    client = FakeSentryClient()
    run_scan(session, client, clips_dir)
    assert [s["query"] for s in client.searches] == ["query on"]


def test_run_scan_bookkeeping_and_progress(session, clips_dir):
    make_video(session, path="D:/footage/a.mp4")
    cat = make_category(session, name="overtaking")
    client = FakeSentryClient(
        matches={"overtaking": [_match(score=0.8, start_s=1.0, end_s=4.0)]}
    )

    events: list[tuple[str, float]] = []
    result = run_scan(
        session,
        client,
        clips_dir,
        categories=[cat],
        progress_cb=lambda msg, frac: events.append((msg, frac)),
    )

    scans = {s.id: s for s in repo.list_scans(session)}
    row = scans[result.scan_id]
    assert row.status == "done"
    assert row.clips_found == 1
    assert row.finished_at is not None
    assert row.params["categories"] == ["overtaking"]
    assert row.params["dedupe_window_s"] == ScanConfig().dedupe_window_s

    assert events[0][0] == "scanning: overtaking"
    assert events[-1] == ("scan complete", 1.0)
