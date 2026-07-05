"""Metadata generation tests: prompt facts and deterministic clamps."""

from __future__ import annotations

from dashpublish.compile.edl import EDL, ClipInfo, EDLSegment
from dashpublish.compile.profiles import Profile
from dashpublish.llm.base import FakeProvider
from dashpublish.metadata.generate import (
    TAGS_TOTAL_MAX_CHARS,
    TITLE_MAX_CHARS,
    VideoMetadata,
    generate_metadata,
)

SHORT = Profile(
    name="short", width=1080, height=1920, max_duration_s=60, target_duration_s=55,
    min_segment_s=2.0, max_segment_s=10.0, vf_chain="crop",
)
LONG = Profile(
    name="long", width=1920, height=1080, max_duration_s=900, target_duration_s=300,
    min_segment_s=4.0, max_segment_s=30.0, vf_chain="scale",
)

CLIPS = {
    1: ClipInfo(id=1, duration_s=10.0, category="crash", score=0.9, clip_path="/c/1.mp4"),
    2: ClipInfo(id=2, duration_s=8.0, category="funny", score=0.7, clip_path="/c/2.mp4"),
}

EDL_OBJ = EDL(
    profile="short",
    target_duration_s=55,
    segments=[
        EDLSegment(clip_id=1, trim_start_s=0.0, trim_end_s=5.0, order=0),
        EDLSegment(clip_id=2, trim_start_s=0.0, trim_end_s=5.0, order=1),
    ],
    rationale="hook first",
)


def test_generate_metadata_happy_path():
    provider = FakeProvider(
        responses=[
            {
                "title": "Insane Dashcam Moments #Shorts",
                "description": "Watch these wild clips.",
                "tags": ["dashcam", "compilation"],
            }
        ]
    )
    meta = generate_metadata(provider, edl=EDL_OBJ, clips=CLIPS, profile=SHORT)
    assert isinstance(meta, VideoMetadata)
    assert meta.title == "Insane Dashcam Moments #Shorts"
    assert meta.tags == ["dashcam", "compilation"]
    # Prompt carries the video facts.
    user = provider.calls[0]["user"]
    assert "crash" in user and "funny" in user
    assert "clip count: 2" in user
    assert "10 s" in user
    assert "dashcam compilation channel" in user


def test_title_clamped_and_shorts_suffix_enforced():
    provider = FakeProvider(responses=[{"title": "x" * 300, "description": "d", "tags": []}])
    meta = generate_metadata(provider, edl=EDL_OBJ, clips=CLIPS, profile=SHORT)
    assert len(meta.title) <= TITLE_MAX_CHARS
    assert meta.title.endswith("#Shorts")


def test_long_profile_no_shorts_suffix():
    provider = FakeProvider(responses=[{"title": "Best Dashcam 2026", "description": "d"}])
    meta = generate_metadata(provider, edl=EDL_OBJ, clips=CLIPS, profile=LONG)
    assert "#Shorts" not in meta.title


def test_tags_deduped_and_total_clamped():
    tags = [f"tag-number-{i:03d}" for i in range(60)]  # 12 chars each -> > 500 total
    tags.insert(1, "TAG-NUMBER-000")  # case-insensitive duplicate
    provider = FakeProvider(responses=[{"title": "t", "description": "d", "tags": tags}])
    meta = generate_metadata(provider, edl=EDL_OBJ, clips=CLIPS, profile=LONG)
    assert len(meta.tags) == len({t.lower() for t in meta.tags})
    assert sum(len(t) for t in meta.tags) <= TAGS_TOTAL_MAX_CHARS
    assert "TAG-NUMBER-000" not in meta.tags


def test_empty_provider_response_falls_back():
    meta = generate_metadata(FakeProvider(), edl=EDL_OBJ, clips=CLIPS, profile=SHORT)
    assert meta.title.startswith("Dashcam Compilation")
    assert meta.title.endswith("#Shorts")
    assert meta.tags == []
