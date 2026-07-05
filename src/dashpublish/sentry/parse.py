"""Defensive parsers for sentrysearch output.

Primary source of truth is ``~/.sentrysearch/last_search.json`` (schema varies by
version, so we accept several shapes); the stdout regex is a fallback.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from dashpublish.db.schemas import SearchMatch
from dashpublish.logging import get_logger

logger = get_logger(__name__)

# --- timestamps -------------------------------------------------------------
_TS_RE = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{2}(?:\.\d+)?)$")


def ts_to_seconds(value: Any) -> float | None:
    """Convert ``"MM:SS"``, ``"HH:MM:SS"``, or a bare number to seconds."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    match = _TS_RE.match(text)
    if match:
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2))
        seconds = float(match.group(3))
        return hours * 3600.0 + minutes * 60.0 + seconds
    try:
        return float(text)
    except ValueError:
        return None


# --- last_search.json -------------------------------------------------------
_SCORE_KEYS = ("score", "similarity", "relevance")
_SOURCE_KEYS = ("source_file", "source", "file", "filename", "video", "path")
_START_KEYS = ("start_s", "start", "start_time", "start_seconds", "from")
_END_KEYS = ("end_s", "end", "end_time", "end_seconds", "to")
_CLIP_KEYS = ("saved_clip_path", "saved_clip", "clip_path", "clip", "output", "saved")
_LIST_KEYS = ("results", "matches", "clips", "items")


def _first_key(entry: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in entry and entry[key] is not None:
            return entry[key]
    return None


def _entry_to_match(entry: Any) -> SearchMatch | None:
    if not isinstance(entry, dict):
        return None
    source = _first_key(entry, _SOURCE_KEYS)
    start = ts_to_seconds(_first_key(entry, _START_KEYS))
    end = ts_to_seconds(_first_key(entry, _END_KEYS))
    if source is None or start is None or end is None:
        logger.warning("skipping unparseable search entry: %r", entry)
        return None
    score_raw = _first_key(entry, _SCORE_KEYS)
    try:
        score = float(score_raw) if score_raw is not None else 0.0
    except (TypeError, ValueError):
        score = 0.0
    clip = _first_key(entry, _CLIP_KEYS)
    return SearchMatch(
        score=score,
        source_file=str(source),
        start_s=start,
        end_s=end,
        saved_clip_path=str(clip) if clip else None,
    )


def parse_last_search(path: Path) -> list[SearchMatch]:
    """Parse sentrysearch's ``last_search.json`` defensively.

    Accepts a top-level list of match dicts, or a dict wrapping such a list under
    ``results``/``matches``/``clips``/``items``. Unknown/malformed entries are
    skipped with a warning; a completely unreadable file yields ``[]``.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("could not read %s: %s", path, exc)
        return []

    if isinstance(data, dict):
        entries: Any = None
        for key in _LIST_KEYS:
            if isinstance(data.get(key), list):
                entries = data[key]
                break
        if entries is None:
            # A dict that itself looks like a single match.
            single = _entry_to_match(data)
            return [single] if single else []
    elif isinstance(data, list):
        entries = data
    else:
        logger.warning("unexpected last_search.json shape: %s", type(data).__name__)
        return []

    matches: list[SearchMatch] = []
    for entry in entries:
        match = _entry_to_match(entry)
        if match is not None:
            matches.append(match)
    return matches


# --- stdout fallback ---------------------------------------------------------
# e.g. "  #1 [0.87] front_2024-01-15_14-30.mp4 @ 02:15-02:45"
_RESULT_RE = re.compile(
    r"#\d+\s+\[(?P<score>[\d.]+)\]\s+(?P<file>.+?)\s+@\s+"
    r"(?P<start>(?:\d+:)?\d{1,2}:\d{2})\s*-\s*(?P<end>(?:\d+:)?\d{1,2}:\d{2})"
)
_SAVED_RE = re.compile(r"Saved clip:\s*(?P<path>.+?)\s*$")


def parse_stdout(text: str) -> list[SearchMatch]:
    """Parse sentrysearch's human-readable search output (fallback path).

    ``Saved clip: <path>`` lines are associated, in order, with the most recent
    match that has no saved clip yet.
    """
    matches: list[SearchMatch] = []
    pending: list[SearchMatch] = []  # matches awaiting a "Saved clip" line

    for line in text.splitlines():
        result = _RESULT_RE.search(line)
        if result:
            start = ts_to_seconds(result.group("start"))
            end = ts_to_seconds(result.group("end"))
            if start is None or end is None:
                continue
            try:
                score = float(result.group("score"))
            except ValueError:
                score = 0.0
            match = SearchMatch(
                score=score,
                source_file=result.group("file").strip(),
                start_s=start,
                end_s=end,
                saved_clip_path=None,
            )
            matches.append(match)
            pending.append(match)
            continue

        saved = _SAVED_RE.search(line)
        if saved and pending:
            target = pending.pop(0)
            target.saved_clip_path = saved.group("path").strip()
    return matches
