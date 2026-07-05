"""Walk a footage tree and classify video files (Tesla events vs generic).

The single entry point is :func:`discover_videos`. Detection is per directory: files
matching the Tesla clip pattern are grouped into multi-camera events; everything else
is treated as generic footage with a best-effort ``recorded_at``.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from dashpublish.ingest.models import DiscoveredVideo
from dashpublish.ingest.tesla import group_tesla_events, parse_tesla_filename
from dashpublish.logging import get_logger

logger = get_logger(__name__)

VIDEO_EXTENSIONS = {".mp4", ".mov"}

# Generic filename timestamp: YYYY[-_]MM[-_]DD[-_ ]HH[-_.]MM([-_.]SS)?
GENERIC_TS_RE = re.compile(
    r"(?P<y>\d{4})[-_](?P<mo>\d{2})[-_](?P<d>\d{2})"
    r"[-_ ](?P<h>\d{2})[-_.](?P<mi>\d{2})(?:[-_.](?P<s>\d{2}))?"
)


def parse_generic_timestamp(name: str) -> datetime | None:
    """Extract a recorded-at datetime from a generic filename, if present."""
    match = GENERIC_TS_RE.search(name)
    if match is None:
        return None
    try:
        return datetime(
            int(match.group("y")),
            int(match.group("mo")),
            int(match.group("d")),
            int(match.group("h")),
            int(match.group("mi")),
            int(match.group("s") or 0),
        )
    except ValueError:
        return None


def _is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTENSIONS


def _mtime(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return None


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def discover_videos(footage_dir: Path) -> list[DiscoveredVideo]:
    """Recursively discover .mp4/.mov files under ``footage_dir``.

    Files matching the Tesla clip filename pattern are grouped (per directory, per
    timestamp prefix) into events; all other video files become generic entries with
    ``recorded_at`` parsed from the filename when possible, else the file mtime.
    Results are sorted by path for determinism.
    """
    footage_dir = Path(footage_dir)
    if not footage_dir.exists():
        logger.warning("footage dir does not exist: %s", footage_dir)
        return []

    all_videos = sorted(
        (p for p in footage_dir.rglob("*") if p.is_file() and _is_video(p)),
        key=lambda p: str(p).lower(),
    )

    tesla_files = [p for p in all_videos if parse_tesla_filename(p) is not None]
    generic_files = [p for p in all_videos if parse_tesla_filename(p) is None]

    discovered: list[DiscoveredVideo] = []

    events = group_tesla_events(tesla_files)
    for event_id, parsed_files in sorted(events.items()):
        for tf in parsed_files:
            discovered.append(
                DiscoveredVideo(
                    path=tf.path,
                    camera=tf.camera,  # type: ignore[arg-type]
                    source_type="tesla_event",
                    event_id=event_id,
                    recorded_at=tf.recorded_at,
                    size_bytes=_size(tf.path),
                )
            )

    for path in generic_files:
        recorded_at = parse_generic_timestamp(path.name) or _mtime(path)
        discovered.append(
            DiscoveredVideo(
                path=path,
                camera="generic",
                source_type="generic",
                event_id=None,
                recorded_at=recorded_at,
                size_bytes=_size(path),
            )
        )

    return discovered
