"""Candidate selection and LLM EDL planning."""

from __future__ import annotations

from typing import Sequence

from pydantic import ValidationError
from sqlalchemy.orm import Session

from dashpublish.compile.edl import (
    EDL,
    ClipInfo,
    EDLValidationError,
    MusicSpec,
    edl_json_schema,
    validate_and_fix,
)
from dashpublish.compile.profiles import Profile
from dashpublish.db import repo
from dashpublish.db.models import Clip
from dashpublish.llm.base import LLMProvider
from dashpublish.llm.prompts import build_edl_prompt

# Selection knobs (deliberately simple; the LLM does the real curation).
CANDIDATE_CAP = 30
TOP_N_PER_CATEGORY = 5
SHORT_PREFERRED_MAX_S = 15.0


def _to_info(clip: Clip) -> ClipInfo:
    return ClipInfo(
        id=clip.id,
        duration_s=max(0.0, clip.end_s - clip.start_s),
        category=clip.category.name if clip.category is not None else None,
        score=clip.score,
        clip_path=clip.clip_path,
    )


def gather_candidates(
    session: Session,
    profile: Profile,
    *,
    clip_ids: Sequence[int] | None = None,
    from_selection: str = "top",
) -> list[ClipInfo]:
    """Collect candidate clips for the planner.

    - ``clip_ids`` given: use exactly those (in order), skipping hidden clips and
      clips without a rendered ``clip_path``.
    - Otherwise: starred clips first, then the top-N per category by score
      (``from_selection="starred"`` restricts to starred only).
    - Only clips with ``clip_path`` set and not hidden are ever considered.
    - Capped at ~30; for the short profile, clips <= 15 s are preferred.
    """
    if clip_ids:
        infos: list[ClipInfo] = []
        for clip_id in clip_ids:
            clip = repo.get_clip(session, clip_id)
            if clip is None or clip.hidden or not clip.clip_path:
                continue
            infos.append(_to_info(clip))
        return infos[:CANDIDATE_CAP]

    usable = [c for c in repo.list_clips(session, hidden=False, sort="score") if c.clip_path]
    starred = [c for c in usable if c.starred]
    if from_selection == "starred":
        pool = list(starred)
    else:
        picked: list[Clip] = []
        per_category: dict[int | None, int] = {}
        for clip in usable:
            if clip.starred:
                continue
            count = per_category.get(clip.category_id, 0)
            if count < TOP_N_PER_CATEGORY:
                per_category[clip.category_id] = count + 1
                picked.append(clip)
        pool = starred + picked

    if profile.name == "short":
        # Stable sort: starred stay first; within each group, prefer <= 15 s clips.
        pool.sort(
            key=lambda c: (
                0 if c.starred else 1,
                0 if (c.end_s - c.start_s) <= SHORT_PREFERRED_MAX_S else 1,
            )
        )
    return [_to_info(c) for c in pool[:CANDIDATE_CAP]]


def plan_edl(
    provider: LLMProvider,
    candidates: Sequence[ClipInfo],
    profile: Profile,
    *,
    music_path: str | None = None,
    transition: str = "cut",
) -> EDL:
    """Ask the LLM for an EDL over ``candidates`` and repair it deterministically."""
    if not candidates:
        raise EDLValidationError("no candidate clips to plan a compilation from")

    system, user = build_edl_prompt(candidates, profile, transition=transition)
    raw = provider.chat_json(system, user, edl_json_schema())

    data = dict(raw)
    # The caller — not the LLM — owns profile, transition, and music.
    data["profile"] = profile.name
    data["transition"] = transition if transition in ("cut", "crossfade") else "cut"
    data.setdefault("target_duration_s", profile.target_duration_s)
    data["music"] = MusicSpec(enabled=music_path is not None, path=music_path).model_dump()
    try:
        edl = EDL.model_validate(data)
    except ValidationError as exc:
        raise EDLValidationError(f"LLM returned an unusable EDL: {exc}") from exc

    clips = {c.id: c for c in candidates}
    return validate_and_fix(edl, clips, profile)
