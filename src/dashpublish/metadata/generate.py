"""AI-generated YouTube metadata (title / description / tags) with hard clamps."""

from __future__ import annotations

from pydantic import BaseModel

from dashpublish.compile.edl import EDL, ClipInfo
from dashpublish.compile.profiles import Profile
from dashpublish.llm.base import LLMProvider
from dashpublish.llm.prompts import build_metadata_prompt

TITLE_MAX_CHARS = 100
DESCRIPTION_MAX_CHARS = 5000
TAG_MAX_CHARS = 100
TAGS_TOTAL_MAX_CHARS = 500  # YouTube counts the total length of all tags.

DEFAULT_TITLE = "Dashcam Compilation"
SHORTS_SUFFIX = " #Shorts"


class VideoMetadata(BaseModel):
    title: str
    description: str
    tags: list[str] = []


def metadata_json_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title", "description", "tags"],
    }


def _clamp_tags(raw_tags: object) -> list[str]:
    """Dedupe, truncate each tag, and keep the total under YouTube's 500-char cap."""
    tags: list[str] = []
    seen: set[str] = set()
    total = 0
    if not isinstance(raw_tags, list):
        return tags
    for item in raw_tags:
        tag = str(item).strip()[:TAG_MAX_CHARS]
        if not tag or tag.lower() in seen:
            continue
        if total + len(tag) > TAGS_TOTAL_MAX_CHARS:
            break
        seen.add(tag.lower())
        tags.append(tag)
        total += len(tag)
    return tags


def generate_metadata(
    provider: LLMProvider,
    *,
    edl: EDL,
    clips: dict[int, ClipInfo],
    profile: Profile,
    channel_hint: str = "dashcam compilation channel",
) -> VideoMetadata:
    """Ask the LLM for metadata, then apply deterministic clamps.

    Clamps: title <= 100 chars (with '#Shorts' guaranteed for the short
    profile), description <= 5000 chars, tags deduped and <= 500 chars total.
    """
    system, user = build_metadata_prompt(
        edl=edl, clips=clips, profile=profile, channel_hint=channel_hint
    )
    raw = provider.chat_json(system, user, metadata_json_schema())

    title = str(raw.get("title") or DEFAULT_TITLE).strip()
    if profile.name == "short" and "#shorts" not in title.lower():
        title = title[: TITLE_MAX_CHARS - len(SHORTS_SUFFIX)].rstrip() + SHORTS_SUFFIX
    title = title[:TITLE_MAX_CHARS]

    description = str(raw.get("description") or "").strip()[:DESCRIPTION_MAX_CHARS]

    return VideoMetadata(title=title, description=description, tags=_clamp_tags(raw.get("tags")))
