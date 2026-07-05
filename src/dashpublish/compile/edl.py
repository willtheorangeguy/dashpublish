"""Edit decision list (EDL): Pydantic models, JSON schema, deterministic repair."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from dashpublish.compile.profiles import Profile

# A segment must play for at least this long to be worth keeping.
MIN_SEGMENT_LEN_S = 1.0


class EDLValidationError(Exception):
    """Raised when an EDL cannot be repaired into something renderable."""


@dataclass(frozen=True)
class ClipInfo:
    """Minimal clip facts the planner/renderer need (decoupled from the ORM)."""

    id: int
    duration_s: float
    category: str | None
    score: float
    clip_path: str | None


class MusicSpec(BaseModel):
    enabled: bool = False
    path: str | None = None
    duck_db: float = -12


class EDLSegment(BaseModel):
    clip_id: int
    trim_start_s: float = 0
    trim_end_s: float
    order: int


class EDL(BaseModel):
    profile: Literal["short", "long"]
    target_duration_s: int
    segments: list[EDLSegment] = Field(min_length=1)
    transition: Literal["cut", "crossfade"] = "cut"
    music: MusicSpec = Field(default_factory=MusicSpec)
    rationale: str = ""


def edl_json_schema() -> dict:
    """JSON schema for the EDL object requested from the LLM.

    Music is decided by the caller (not the LLM), so it is not part of the
    requested schema; :func:`dashpublish.compile.planner.plan_edl` fills it in.
    """
    return {
        "type": "object",
        "properties": {
            "profile": {"type": "string", "enum": ["short", "long"]},
            "target_duration_s": {"type": "integer"},
            "segments": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "clip_id": {"type": "integer"},
                        "trim_start_s": {"type": "number"},
                        "trim_end_s": {"type": "number"},
                        "order": {"type": "integer"},
                    },
                    "required": ["clip_id", "trim_end_s", "order"],
                },
            },
            "transition": {"type": "string", "enum": ["cut", "crossfade"]},
            "rationale": {"type": "string"},
        },
        "required": ["profile", "target_duration_s", "segments"],
    }


def _segment_len(seg: EDLSegment) -> float:
    return seg.trim_end_s - seg.trim_start_s


def validate_and_fix(edl: EDL, clips: dict[int, ClipInfo], profile: Profile) -> EDL:
    """Deterministically repair an LLM-produced EDL against known clips.

    - Drops segments referencing unknown clip ids.
    - Clamps trims into ``[0, clip duration]`` and enforces
      ``trim_end - trim_start >= 1s`` (segments on clips shorter than 1s are dropped).
    - Clamps segment length to ``profile.max_segment_s``.
    - Re-numbers ``order`` sequentially from 0 (sorted by the original order).
    - If the total exceeds ``profile.max_duration_s``, trims the last segment
      and/or drops segments from the end until it fits.

    Raises :class:`EDLValidationError` if no renderable segment survives.
    """
    fixed: list[EDLSegment] = []
    for seg in sorted(edl.segments, key=lambda s: s.order):
        info = clips.get(seg.clip_id)
        if info is None:
            continue
        duration = max(0.0, info.duration_s)
        start = min(max(seg.trim_start_s, 0.0), duration)
        end = min(max(seg.trim_end_s, 0.0), duration)
        if end <= start:
            end = min(duration, start + MIN_SEGMENT_LEN_S)
        if end - start < MIN_SEGMENT_LEN_S:
            start = max(0.0, end - MIN_SEGMENT_LEN_S)
        if end - start < MIN_SEGMENT_LEN_S:
            continue  # clip itself is too short to use
        if end - start > profile.max_segment_s:
            end = start + profile.max_segment_s
        fixed.append(
            EDLSegment(clip_id=seg.clip_id, trim_start_s=start, trim_end_s=end, order=len(fixed))
        )

    total = sum(_segment_len(s) for s in fixed)
    while fixed and total > profile.max_duration_s:
        last = fixed[-1]
        seg_len = _segment_len(last)
        allowed = profile.max_duration_s - (total - seg_len)
        if allowed >= MIN_SEGMENT_LEN_S:
            fixed[-1] = last.model_copy(update={"trim_end_s": last.trim_start_s + allowed})
            total = total - seg_len + allowed
        else:
            fixed.pop()
            total -= seg_len

    if not fixed:
        raise EDLValidationError("no valid segments remain after validation")
    return edl.model_copy(update={"segments": fixed})
