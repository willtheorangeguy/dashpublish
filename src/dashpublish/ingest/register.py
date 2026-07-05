"""Register discovered footage into the videos table.

``register_footage`` walks the footage tree, keeps only the preferred camera for
Tesla events (front when available), computes a cheap content hash, probes duration
via ffprobe when available, and upserts each file keyed on its absolute path.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

from sqlalchemy.orm import Session

from dashpublish.db import repo
from dashpublish.ingest.discovery import discover_videos
from dashpublish.ingest.models import DiscoveredVideo, RegisterResult
from dashpublish.ingest.tesla import preferred_camera_paths
from dashpublish.logging import get_logger

logger = get_logger(__name__)

_HASH_BYTES = 1024 * 1024  # first 1 MiB


def content_hash(path: Path) -> str | None:
    """Cheap content fingerprint: sha256 of the first 1 MiB plus the file size."""
    try:
        size = path.stat().st_size
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            digest.update(fh.read(_HASH_BYTES))
        digest.update(str(size).encode("ascii"))
        return digest.hexdigest()
    except OSError:
        logger.warning("could not hash %s", path)
        return None


def probe_duration(path: Path, timeout_s: float = 30.0) -> float | None:
    """Return the media duration in seconds via ffprobe, or ``None`` on any failure."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        proc = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        if proc.returncode != 0:
            return None
        return float(proc.stdout.strip())
    except (OSError, subprocess.TimeoutExpired, ValueError):
        logger.warning("ffprobe failed for %s", path)
        return None


def _select_registrable(discovered: list[DiscoveredVideo]) -> list[DiscoveredVideo]:
    """Keep generic files as-is; for Tesla events keep only the preferred camera(s)."""
    generic = [d for d in discovered if d.source_type != "tesla_event"]

    by_event: dict[str, list[DiscoveredVideo]] = {}
    for d in discovered:
        if d.source_type == "tesla_event" and d.event_id is not None:
            by_event.setdefault(d.event_id, []).append(d)

    selected: list[DiscoveredVideo] = list(generic)
    for members in by_event.values():
        keep = set(preferred_camera_paths([m.path for m in members]))
        selected.extend(m for m in members if m.path in keep)
    return selected


def register_footage(session: Session, footage_dir: Path) -> RegisterResult:
    """Discover footage under ``footage_dir`` and upsert video rows.

    Returns counts of newly inserted vs previously seen files. Tesla events register
    only their preferred (front) camera files.
    """
    discovered = discover_videos(Path(footage_dir))
    selected = _select_registrable(discovered)

    existing = {v.path for v in repo.list_videos(session)}
    new = 0
    seen = 0
    for d in selected:
        path_str = str(d.path.resolve())
        already = path_str in existing
        # NOTE: the Video model has no size_bytes column; the size is folded into
        # content_hash instead (sha256 of first 1 MiB + size).
        repo.upsert_video(
            session,
            path_str,
            camera=d.camera,
            source_type=d.source_type,
            event_id=d.event_id,
            recorded_at=d.recorded_at,
            content_hash=content_hash(d.path),
            duration_s=probe_duration(d.path),
        )
        if already:
            seen += 1
        else:
            new += 1

    logger.info(
        "registered footage from %s: %d new, %d seen, %d total",
        footage_dir,
        new,
        seen,
        len(selected),
    )
    return RegisterResult(new=new, seen=seen, total=len(selected))
