"""Tesla dashcam filename parsing and multi-camera event grouping.

Tesla saves clips like ``2024-01-15_14-30-05-front.mp4`` (also ``-back``,
``-left_repeater``, ``-right_repeater``), typically under ``SavedClips/<timestamp>/``
or ``SentryClips/<timestamp>/``. Files sharing a timestamp prefix belong to the same
event; we prefer the front camera when building compilations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Tesla cameras, in preference order.
TESLA_CAMERAS = ("front", "back", "left_repeater", "right_repeater")

# e.g. 2024-01-15_14-30-05-front.mp4
TESLA_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})"
    r"-(?P<cam>front|back|left_repeater|right_repeater)"
    r"\.(?:mp4|mov)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TeslaFile:
    """A parsed Tesla clip filename."""

    path: Path
    timestamp: str
    camera: str
    recorded_at: datetime


def parse_tesla_filename(path: Path) -> TeslaFile | None:
    """Parse a Tesla clip filename, or return ``None`` if it does not match."""
    match = TESLA_RE.match(path.name)
    if match is None:
        return None
    ts = match.group("ts")
    camera = match.group("cam").lower()
    try:
        recorded_at = datetime.strptime(ts, "%Y-%m-%d_%H-%M-%S")
    except ValueError:
        return None
    return TeslaFile(path=path, timestamp=ts, camera=camera, recorded_at=recorded_at)


def make_event_id(timestamp: str, parent: Path) -> str:
    """Build a stable event id from a timestamp prefix and its parent directory."""
    return f"{timestamp}@{parent.name}" if parent.name else timestamp


def group_tesla_events(files: list[Path]) -> dict[str, list[TeslaFile]]:
    """Group Tesla files (from any directories) into events.

    The event key is the timestamp prefix combined with the file's parent directory,
    so two events that happen to share a timestamp under different folders stay
    distinct. Non-matching files are ignored.
    """
    events: dict[str, list[TeslaFile]] = {}
    for path in files:
        parsed = parse_tesla_filename(path)
        if parsed is None:
            continue
        event_id = make_event_id(parsed.timestamp, path.parent)
        events.setdefault(event_id, []).append(parsed)
    return events


def preferred_camera_paths(event_files: list[Path]) -> list[Path]:
    """Return the front-camera path only if present, else all supplied paths.

    Files that do not parse as Tesla clips are treated as non-front and only returned
    in the fallback (no front camera) case.
    """
    front: list[Path] = []
    for path in event_files:
        parsed = parse_tesla_filename(path)
        if parsed is not None and parsed.camera == "front":
            front.append(path)
    if front:
        return front
    return list(event_files)
