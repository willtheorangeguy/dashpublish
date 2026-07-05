"""Planner tests: gather_candidates selection rules and plan_edl via FakeProvider."""

from __future__ import annotations

import pytest

from dashpublish.compile.edl import EDLValidationError
from dashpublish.compile.planner import gather_candidates, plan_edl
from dashpublish.compile.profiles import Profile
from dashpublish.testing import FakeProvider, make_category, make_clip

SHORT = Profile(
    name="short", width=1080, height=1920, max_duration_s=60, target_duration_s=55,
    min_segment_s=2.0, max_segment_s=10.0, vf_chain="crop",
)
LONG = Profile(
    name="long", width=1920, height=1080, max_duration_s=900, target_duration_s=300,
    min_segment_s=4.0, max_segment_s=30.0, vf_chain="scale",
)


def clip(session, **kw):
    kw.setdefault("clip_path", "/clips/x.mp4")
    return make_clip(session, **kw)


def test_gather_starred_first_hidden_and_pathless_excluded(session):
    cat = make_category(session, name="near-miss")
    starred = clip(session, category_id=cat.id, score=0.5, starred=True)
    top = clip(session, category_id=cat.id, score=0.99)
    clip(session, category_id=cat.id, score=0.98, hidden=True)
    clip(session, category_id=cat.id, score=0.97, clip_path=None)

    infos = gather_candidates(session, LONG)
    ids = [i.id for i in infos]
    assert ids[0] == starred.id  # starred first despite lower score
    assert top.id in ids
    assert len(ids) == 2  # hidden + pathless excluded
    assert infos[0].category == "near-miss"


def test_gather_top_n_per_category(session):
    cat = make_category(session, name="overtaking")
    for i in range(8):
        clip(session, category_id=cat.id, score=0.9 - i * 0.01)
    infos = gather_candidates(session, LONG)
    assert len(infos) == 5  # TOP_N_PER_CATEGORY
    scores = [i.score for i in infos]
    assert scores == sorted(scores, reverse=True)


def test_gather_explicit_clip_ids_keeps_order(session):
    a = clip(session, score=0.1)
    b = clip(session, score=0.9)
    hidden = clip(session, score=0.9, hidden=True)
    infos = gather_candidates(session, LONG, clip_ids=[b.id, a.id, hidden.id, 12345])
    assert [i.id for i in infos] == [b.id, a.id]


def test_gather_from_selection_starred_only(session):
    starred = clip(session, score=0.2, starred=True)
    clip(session, score=0.9)
    infos = gather_candidates(session, LONG, from_selection="starred")
    assert [i.id for i in infos] == [starred.id]


def test_gather_short_profile_prefers_short_clips(session):
    long_clip = clip(session, score=0.99, start_s=0.0, end_s=20.0)
    short_clip = clip(session, score=0.5, start_s=0.0, end_s=5.0)
    infos = gather_candidates(session, SHORT)
    assert [i.id for i in infos] == [short_clip.id, long_clip.id]

    # But starred long clips still come before unstarred short ones.
    starred_long = clip(session, score=0.1, start_s=0.0, end_s=20.0, starred=True)
    infos = gather_candidates(session, SHORT)
    assert infos[0].id == starred_long.id


def test_plan_edl_uses_provider_and_fixes_result(session):
    cat = make_category(session, name="crash")
    c1 = clip(session, category_id=cat.id, score=0.9, start_s=0.0, end_s=12.0)
    c2 = clip(session, category_id=cat.id, score=0.8, start_s=0.0, end_s=6.0)
    candidates = gather_candidates(session, SHORT)

    canned = {
        "profile": "long",  # planner must force the real profile
        "target_duration_s": 55,
        "segments": [
            {"clip_id": c1.id, "trim_start_s": 0, "trim_end_s": 25.0, "order": 0},
            {"clip_id": c2.id, "trim_start_s": 1.0, "trim_end_s": 5.0, "order": 1},
            {"clip_id": 424242, "trim_start_s": 0, "trim_end_s": 5.0, "order": 2},
        ],
        "rationale": "canned",
    }
    provider = FakeProvider(responses=[canned])
    edl = plan_edl(provider, candidates, SHORT, music_path="/music/track.mp3")

    assert edl.profile == "short"
    assert edl.transition == "cut"
    assert edl.music.enabled is True
    assert edl.music.path == "/music/track.mp3"
    assert [s.clip_id for s in edl.segments] == [c1.id, c2.id]  # unknown dropped
    first = edl.segments[0]
    assert first.trim_end_s - first.trim_start_s <= SHORT.max_segment_s
    assert edl.rationale == "canned"

    # Prompt carried candidates + schema.
    call = provider.calls[0]
    assert f'"id": {c1.id}' in call["user"]
    assert "segments" in call["schema"]["properties"]


def test_plan_edl_no_music(session):
    c1 = clip(session, score=0.9)
    candidates = gather_candidates(session, SHORT)
    provider = FakeProvider(
        responses=[
            {
                "profile": "short",
                "target_duration_s": 55,
                "segments": [{"clip_id": c1.id, "trim_start_s": 0, "trim_end_s": 5, "order": 0}],
            }
        ]
    )
    edl = plan_edl(provider, candidates, SHORT)
    assert edl.music.enabled is False
    assert edl.music.path is None


def test_plan_edl_empty_candidates_raises():
    with pytest.raises(EDLValidationError):
        plan_edl(FakeProvider(), [], SHORT)


def test_plan_edl_unusable_response_raises(session):
    c1 = clip(session, score=0.9)
    candidates = gather_candidates(session, SHORT)
    provider = FakeProvider(responses=[{"totally": "wrong"}])
    with pytest.raises(EDLValidationError):
        plan_edl(provider, candidates, SHORT)
    assert c1.id  # session used
