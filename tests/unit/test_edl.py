"""EDL validation-and-repair tests."""

from __future__ import annotations

import pytest

from dashpublish.compile.edl import (
    EDL,
    ClipInfo,
    EDLSegment,
    EDLValidationError,
    edl_json_schema,
    validate_and_fix,
)
from dashpublish.compile.profiles import Profile

SHORT = Profile(
    name="short",
    width=1080,
    height=1920,
    max_duration_s=60,
    target_duration_s=55,
    min_segment_s=2.0,
    max_segment_s=10.0,
    vf_chain="crop=ih*9/16:ih,scale=1080:1920,setsar=1,fps=30",
)


def info(clip_id: int, duration: float = 12.0) -> ClipInfo:
    return ClipInfo(
        id=clip_id, duration_s=duration, category="near-miss", score=0.8,
        clip_path=f"/clips/{clip_id}.mp4",
    )


def make_edl(segments: list[EDLSegment]) -> EDL:
    return EDL(profile="short", target_duration_s=55, segments=segments)


def seg(clip_id: int, start: float, end: float, order: int) -> EDLSegment:
    return EDLSegment(clip_id=clip_id, trim_start_s=start, trim_end_s=end, order=order)


def test_unknown_clip_dropped():
    edl = make_edl([seg(1, 0, 5, 0), seg(99, 0, 5, 1), seg(2, 0, 5, 2)])
    fixed = validate_and_fix(edl, {1: info(1), 2: info(2)}, SHORT)
    assert [s.clip_id for s in fixed.segments] == [1, 2]
    assert [s.order for s in fixed.segments] == [0, 1]


def test_trims_clamped_into_clip_duration():
    edl = make_edl([seg(1, -3.0, 50.0, 0)])
    fixed = validate_and_fix(edl, {1: info(1, duration=8.0)}, SHORT)
    s = fixed.segments[0]
    assert s.trim_start_s == 0.0
    assert s.trim_end_s == 8.0


def test_inverted_trim_fixed_to_min_length():
    edl = make_edl([seg(1, 5.0, 3.0, 0)])
    fixed = validate_and_fix(edl, {1: info(1, duration=12.0)}, SHORT)
    s = fixed.segments[0]
    assert s.trim_end_s > s.trim_start_s
    assert s.trim_end_s - s.trim_start_s >= 1.0


def test_segment_clamped_to_profile_max_segment():
    edl = make_edl([seg(1, 0.0, 25.0, 0)])
    fixed = validate_and_fix(edl, {1: info(1, duration=30.0)}, SHORT)
    s = fixed.segments[0]
    assert s.trim_end_s - s.trim_start_s == pytest.approx(SHORT.max_segment_s)


def test_over_duration_trimmed_to_fit_short_profile():
    # 8 segments x 10 s = 80 s > 60 s max: last segment trimmed, overflow dropped.
    segments = [seg(i, 0.0, 10.0, i) for i in range(1, 9)]
    clips = {i: info(i, duration=12.0) for i in range(1, 9)}
    fixed = validate_and_fix(make_edl(segments), clips, SHORT)
    total = sum(s.trim_end_s - s.trim_start_s for s in fixed.segments)
    assert total <= SHORT.max_duration_s
    assert total == pytest.approx(SHORT.max_duration_s)
    assert len(fixed.segments) == 6
    assert [s.order for s in fixed.segments] == list(range(6))


def test_segments_reordered_by_order_field():
    edl = make_edl([seg(2, 0, 4, 5), seg(1, 0, 4, 1)])
    fixed = validate_and_fix(edl, {1: info(1), 2: info(2)}, SHORT)
    assert [s.clip_id for s in fixed.segments] == [1, 2]
    assert [s.order for s in fixed.segments] == [0, 1]


def test_too_short_clip_dropped():
    edl = make_edl([seg(1, 0.0, 0.5, 0), seg(2, 0.0, 5.0, 1)])
    fixed = validate_and_fix(edl, {1: info(1, duration=0.5), 2: info(2)}, SHORT)
    assert [s.clip_id for s in fixed.segments] == [2]


def test_nothing_survives_raises():
    edl = make_edl([seg(99, 0, 5, 0)])
    with pytest.raises(EDLValidationError):
        validate_and_fix(edl, {1: info(1)}, SHORT)


def test_edl_requires_at_least_one_segment():
    with pytest.raises(Exception):
        EDL(profile="short", target_duration_s=55, segments=[])


def test_edl_json_schema_shape():
    schema = edl_json_schema()
    assert schema["type"] == "object"
    assert set(schema["required"]) == {"profile", "target_duration_s", "segments"}
    item_props = schema["properties"]["segments"]["items"]["properties"]
    assert {"clip_id", "trim_start_s", "trim_end_s", "order"} <= set(item_props)
