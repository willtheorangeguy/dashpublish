"""Prompt builders for EDL planning and video metadata generation."""

from __future__ import annotations

import json
from collections import Counter
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:  # pragma: no cover
    from dashpublish.compile.edl import EDL, ClipInfo
    from dashpublish.compile.profiles import Profile

EDL_SYSTEM_PROMPT = (
    "You are an expert dashcam-compilation video editor. You plan tight, engaging "
    "edits from a list of candidate clips.\n"
    "Editing rules:\n"
    "- Open with the strongest clip (highest score) as the hook — this matters most "
    "for short-form vertical video.\n"
    "- Build variety: avoid placing two clips of the same category back-to-back.\n"
    "- Keep pacing snappy; trim dead time at the start and end of clips.\n"
    "- Hit the target total duration as closely as possible and NEVER exceed the "
    "hard maximum.\n"
    "- Respect the per-segment length limits.\n"
    "- Use each clip at most once.\n"
    "Output ONLY a JSON object matching the provided schema — no prose, no markdown."
)

METADATA_SYSTEM_PROMPT = (
    "You are a YouTube growth expert writing metadata for a dashcam compilation "
    "channel. Write a punchy, clickable (but honest) title, an informative "
    "description, and relevant search tags.\n"
    "Rules:\n"
    "- Title: at most 100 characters.\n"
    "- Description: 2-5 short paragraphs or lines; may include a few hashtags.\n"
    "- Tags: 10-20 short keyword phrases, no '#' prefix, at most 500 characters total.\n"
    "- For short-form (vertical) videos, include '#Shorts' in the title and description.\n"
    "Output ONLY a JSON object matching the provided schema — no prose, no markdown."
)


def build_edl_prompt(
    candidates: Sequence["ClipInfo"],
    profile: "Profile",
    *,
    transition: str = "cut",
) -> tuple[str, str]:
    """Return ``(system, user)`` messages for EDL planning."""
    candidate_rows = [
        {
            "id": c.id,
            "category": c.category,
            "score": round(c.score, 3),
            "duration_s": round(c.duration_s, 2),
        }
        for c in candidates
    ]
    user = (
        f"Plan a {profile.name}-form dashcam compilation "
        f"({profile.width}x{profile.height}).\n\n"
        "Constraints:\n"
        f'- profile: "{profile.name}"\n'
        f"- target total duration: {profile.target_duration_s} s "
        f"(hard maximum {profile.max_duration_s} s)\n"
        f"- per-segment length: {profile.min_segment_s:g} to {profile.max_segment_s:g} s\n"
        f'- transition: "{transition}"\n'
        "- trim_start_s / trim_end_s are relative to each clip file and must lie "
        "within its duration_s\n"
        '- "order" starts at 0 and increases by 1\n\n'
        "Candidate clips (JSON):\n"
        f"{json.dumps(candidate_rows, indent=2)}\n\n"
        "Return the EDL JSON object now."
    )
    return EDL_SYSTEM_PROMPT, user


def build_metadata_prompt(
    *,
    edl: "EDL",
    clips: dict[int, "ClipInfo"],
    profile: "Profile",
    channel_hint: str = "dashcam compilation channel",
) -> tuple[str, str]:
    """Return ``(system, user)`` messages for title/description/tags generation."""
    categories = Counter(
        (clips[s.clip_id].category or "misc")
        for s in edl.segments
        if s.clip_id in clips
    )
    total_s = sum(s.trim_end_s - s.trim_start_s for s in edl.segments)
    category_mix = ", ".join(f"{name} x{count}" for name, count in categories.most_common())
    user = (
        f"Write YouTube metadata for a {profile.name}-form dashcam compilation "
        f"({profile.width}x{profile.height}) on a {channel_hint}.\n\n"
        f"Video facts:\n"
        f"- clip count: {len(edl.segments)}\n"
        f"- total duration: {total_s:.0f} s\n"
        f"- category mix: {category_mix or 'mixed dashcam moments'}\n"
        f"- editor rationale: {edl.rationale or 'n/a'}\n\n"
        "Return the metadata JSON object now."
    )
    return METADATA_SYSTEM_PROMPT, user
