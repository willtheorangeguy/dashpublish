"""Tests for dashpublish.db.repo."""

from __future__ import annotations

from dashpublish.db import repo
from dashpublish.db.schemas import CategoryIn, ClipPatch


def test_upsert_video_idempotent(session):
    v1 = repo.upsert_video(session, "/footage/a.mp4", duration_s=30.0)
    v2 = repo.upsert_video(session, "/footage/a.mp4", duration_s=45.0)
    assert v1.id == v2.id
    assert v2.duration_s == 45.0
    assert len(repo.list_videos(session)) == 1


def test_unindexed_and_mark_indexed(session):
    v = repo.upsert_video(session, "/footage/a.mp4")
    assert [x.id for x in repo.get_unindexed_videos(session)] == [v.id]
    repo.mark_indexed(session, v.id)
    assert repo.get_unindexed_videos(session) == []


def test_seed_default_categories_idempotent(session):
    first = repo.seed_default_categories(session)
    assert {c.name for c in first} == {
        "overtaking",
        "high-speed",
        "cut-off",
        "near-miss",
        "tailgating",
        "red-light",
        "crash",
        "funny",
    }
    assert all(c.is_builtin for c in first)
    assert all(c.threshold == 0.5 and c.save_top == 3 and c.enabled for c in first)

    second = repo.seed_default_categories(session)
    assert len(repo.list_categories(session)) == 8
    assert {c.id for c in first} == {c.id for c in second}


def test_category_crud(session):
    cat = repo.create_category(
        session, CategoryIn(name="custom", query_text="something interesting")
    )
    assert cat.id is not None
    assert cat.is_builtin is False
    repo.update_category(session, cat.id, enabled=False, threshold=0.9)
    reloaded = repo.get_category(session, cat.id)
    assert reloaded.enabled is False
    assert reloaded.threshold == 0.9
    assert repo.delete_category(session, cat.id) is True
    assert repo.get_category(session, cat.id) is None


def test_dedupe_keeps_highest_and_merges_category(session):
    v = repo.upsert_video(session, "/footage/a.mp4")
    cat_over = repo.create_category(session, CategoryIn(name="overtaking", query_text="q"))
    cat_near = repo.create_category(session, CategoryIn(name="near-miss", query_text="q"))

    # Low-score clip lands first in the time bucket.
    c1 = repo.upsert_clip_deduped(
        session,
        video_id=v.id,
        category_id=cat_over.id,
        category_name="overtaking",
        score=0.6,
        start_s=10.0,
        end_s=15.0,
        window=3,
    )
    # Higher-score clip in the same bucket wins; loser merged into "also".
    c2 = repo.upsert_clip_deduped(
        session,
        video_id=v.id,
        category_id=cat_near.id,
        category_name="near-miss",
        score=0.9,
        start_s=11.0,
        end_s=16.0,
        window=3,
    )
    assert c1.id == c2.id  # same dedupe bucket
    assert c2.score == 0.9
    assert c2.category_id == cat_near.id
    assert c2.user_tags["also"] == ["overtaking"]

    # A third, lower-score clip in the same bucket only appends to "also".
    c3 = repo.upsert_clip_deduped(
        session,
        video_id=v.id,
        category_id=cat_over.id,
        category_name="tailgating",
        score=0.5,
        start_s=11.5,
        end_s=17.0,
        window=3,
    )
    assert c3.id == c2.id
    assert c3.score == 0.9
    assert set(c3.user_tags["also"]) == {"overtaking", "tailgating"}

    assert len(repo.list_clips(session)) == 1


def test_dedupe_separate_buckets(session):
    v = repo.upsert_video(session, "/footage/a.mp4")
    repo.upsert_clip_deduped(
        session, video_id=v.id, score=0.6, start_s=1.0, end_s=2.0, window=3
    )
    repo.upsert_clip_deduped(
        session, video_id=v.id, score=0.6, start_s=20.0, end_s=21.0, window=3
    )
    assert len(repo.list_clips(session)) == 2


def test_list_clips_filters_and_sort(session):
    v = repo.upsert_video(session, "/footage/a.mp4")
    cat = repo.create_category(session, CategoryIn(name="overtaking", query_text="q"))
    a = repo.upsert_clip_deduped(
        session, video_id=v.id, category_id=cat.id, score=0.9, start_s=1.0, end_s=2.0,
        window=3,
    )
    b = repo.upsert_clip_deduped(
        session, video_id=v.id, score=0.4, start_s=30.0, end_s=31.0, window=3
    )
    repo.patch_clip(session, a.id, ClipPatch(starred=True))
    repo.patch_clip(session, b.id, ClipPatch(hidden=True))

    starred = repo.list_clips(session, starred=True)
    assert [c.id for c in starred] == [a.id]

    by_cat = repo.list_clips(session, category="overtaking")
    assert [c.id for c in by_cat] == [a.id]

    min_scored = repo.list_clips(session, min_score=0.5)
    assert [c.id for c in min_scored] == [a.id]

    ordered = repo.list_clips(session, sort="score")
    assert [c.id for c in ordered] == [a.id, b.id]

    by_start = repo.list_clips(session, sort="start")
    assert [c.id for c in by_start] == [a.id, b.id]


def test_patch_clip_tags(session):
    v = repo.upsert_video(session, "/footage/a.mp4")
    clip = repo.upsert_clip_deduped(
        session, video_id=v.id, score=0.5, start_s=1.0, end_s=2.0, window=3
    )
    patched = repo.patch_clip(
        session, clip.id, ClipPatch(user_tags={"note": "great"}, starred=True)
    )
    assert patched.starred is True
    assert patched.user_tags == {"note": "great"}


def test_scan_lifecycle(session):
    scan = repo.create_scan(session, params={"threshold": 0.5})
    assert scan.status == "running"
    finished = repo.finish_scan(session, scan.id, status="done", clips_found=3)
    assert finished.status == "done"
    assert finished.clips_found == 3
    assert finished.finished_at is not None


def test_compilation_lifecycle_status_transitions(session):
    comp = repo.create_compilation(session, profile="short", title="My Comp")
    assert comp.status == "draft"

    v = repo.upsert_video(session, "/footage/a.mp4")
    clip = repo.upsert_clip_deduped(
        session, video_id=v.id, score=0.8, start_s=1.0, end_s=6.0, window=3
    )
    added = repo.add_compilation_clips(
        session, comp.id, [{"clip_id": clip.id, "trim_start": 0.0, "trim_end": 4.0}]
    )
    assert added[0].order_index == 0

    for status in ("planning", "rendering", "rendered", "uploaded", "published"):
        repo.update_compilation(session, comp.id, status=status)
        assert repo.get_compilation(session, comp.id).status == status

    repo.update_compilation(
        session, comp.id, edl_json={"segments": []}, output_path="/out.mp4"
    )
    reloaded = repo.get_compilation(session, comp.id)
    assert reloaded.output_path == "/out.mp4"
    assert reloaded.edl_json == {"segments": []}
    assert len(repo.list_compilation_clips(session, comp.id)) == 1


def test_publish_record_lifecycle(session):
    comp = repo.create_compilation(session, profile="long")
    rec = repo.create_publish_record(
        session,
        compilation_id=comp.id,
        title="Best clips",
        tags_json=["dashcam", "cars"],
    )
    assert rec.privacy_status == "private"
    repo.update_publish_record(
        session, rec.id, youtube_video_id="yt123", privacy_status="public"
    )
    records = repo.list_publish_records(session, compilation_id=comp.id)
    assert records[0].youtube_video_id == "yt123"
    assert records[0].privacy_status == "public"


def test_settings_get_set(session):
    assert repo.get_setting(session, "missing", default="fallback") == "fallback"
    repo.set_setting(session, "theme", {"dark": True})
    assert repo.get_setting(session, "theme") == {"dark": True}
    repo.set_setting(session, "theme", {"dark": False})
    assert repo.get_setting(session, "theme") == {"dark": False}
    assert len(repo.list_settings(session)) == 1
