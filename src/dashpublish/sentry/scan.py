"""Detection scan: run category queries through sentrysearch and persist clips.

Searches run sequentially (sentrysearch overwrites ``last_search.json`` per search)
and saved clips are copied into our own clips directory immediately.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from sqlalchemy.orm import Session

from dashpublish.config import ScanConfig
from dashpublish.db import repo
from dashpublish.db.models import Category, Video
from dashpublish.db.schemas import SearchMatch
from dashpublish.logging import get_logger

logger = get_logger(__name__)

ProgressCb = Callable[[str, float], None]


@dataclass
class ScanResult:
    """Outcome of one detection scan."""

    scan_id: int
    clips_found: int
    categories_run: int
    errors: list[str] = field(default_factory=list)


def _notify(progress_cb: ProgressCb | None, message: str, fraction: float) -> None:
    if progress_cb is not None:
        try:
            progress_cb(message, fraction)
        except Exception:  # noqa: BLE001 - progress must never break a scan
            logger.exception("progress callback failed")


def ensure_indexed(
    session: Session,
    client,
    *,
    progress_cb: ProgressCb | None = None,
) -> int:
    """Index every video with ``indexed_at IS NULL`` and mark it indexed.

    Returns the number of videos indexed.
    """
    videos = repo.get_unindexed_videos(session)
    total = len(videos)
    for i, video in enumerate(videos):
        _notify(progress_cb, f"indexing {video.path}", i / total if total else 1.0)
        client.index(video.path)
        repo.mark_indexed(session, video.id)
    _notify(progress_cb, "indexing complete", 1.0)
    return total


def _video_lookup(session: Session) -> tuple[dict[str, Video], dict[str, list[Video]]]:
    """Build lookups by normalized full path and by basename."""
    by_path: dict[str, Video] = {}
    by_name: dict[str, list[Video]] = {}
    for video in repo.list_videos(session):
        normalized = str(Path(video.path)).lower()
        by_path[normalized] = video
        by_name.setdefault(Path(video.path).name.lower(), []).append(video)
    return by_path, by_name


def _resolve_video(
    match: SearchMatch,
    by_path: dict[str, Video],
    by_name: dict[str, list[Video]],
) -> Video | None:
    """Find the videos row for a match's source_file (full path or basename)."""
    source = match.source_file
    normalized = str(Path(source)).lower()
    video = by_path.get(normalized)
    if video is not None:
        return video
    candidates = by_name.get(Path(source).name.lower(), [])
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        logger.warning(
            "ambiguous basename %r matches %d videos; using first",
            source,
            len(candidates),
        )
        return candidates[0]
    return None


def _copy_clip(
    match: SearchMatch, clips_dir: Path, video_id: int, category_name: str
) -> str | None:
    """Copy the sentrysearch-saved clip into our clips dir; None if unavailable."""
    if not match.saved_clip_path:
        return None
    source = Path(match.saved_clip_path)
    if not source.exists():
        logger.warning("saved clip missing on disk: %s", source)
        return None
    clips_dir.mkdir(parents=True, exist_ok=True)
    dest = clips_dir / f"clip_{video_id}_{category_name}_{int(match.start_s)}s.mp4"
    try:
        shutil.copy2(source, dest)
    except OSError:
        logger.warning("failed to copy clip %s -> %s", source, dest)
        return None
    return str(dest)


def run_scan(
    session: Session,
    client,
    clips_dir: Path,
    *,
    categories: list[Category] | None = None,
    scan_cfg: ScanConfig | None = None,
    progress_cb: ProgressCb | None = None,
) -> ScanResult:
    """Run every enabled category query through ``client`` and upsert clips.

    Per-category failures are recorded and the scan continues; the scan row ends in
    status ``"done"`` (no errors) or ``"partial"``.
    """
    scan_cfg = scan_cfg or ScanConfig()
    cats = categories if categories is not None else repo.list_categories(
        session, enabled_only=True
    )

    scan = repo.create_scan(
        session,
        params={
            "categories": [c.name for c in cats],
            "dedupe_window_s": scan_cfg.dedupe_window_s,
            "default_threshold": scan_cfg.default_threshold,
        },
    )

    by_path, by_name = _video_lookup(session)
    clips_dir = Path(clips_dir)
    errors: list[str] = []
    clip_ids: set[int] = set()

    total = len(cats)
    for i, cat in enumerate(cats):
        _notify(progress_cb, f"scanning: {cat.name}", i / total if total else 1.0)
        try:
            matches = client.search(
                cat.query_text,
                threshold=cat.threshold,
                save_top=cat.save_top,
                rerank=cat.rerank,
            )
        except Exception as exc:  # noqa: BLE001 - keep scanning other categories
            logger.exception("category %s failed", cat.name)
            errors.append(f"{cat.name}: {exc}")
            continue

        for match in matches:
            video = _resolve_video(match, by_path, by_name)
            if video is None:
                logger.warning(
                    "no registered video for match source %r (category %s); skipping",
                    match.source_file,
                    cat.name,
                )
                continue
            clip_path = _copy_clip(match, clips_dir, video.id, cat.name)
            clip = repo.upsert_clip_deduped(
                session,
                video_id=video.id,
                category_id=cat.id,
                category_name=cat.name,
                score=match.score,
                start_s=match.start_s,
                end_s=match.end_s,
                window=scan_cfg.dedupe_window_s,
                clip_path=clip_path,
                scan_id=scan.id,
            )
            clip_ids.add(clip.id)

    status = "partial" if errors else "done"
    repo.finish_scan(
        session,
        scan.id,
        status=status,
        clips_found=len(clip_ids),
        error="; ".join(errors) if errors else None,
    )
    _notify(progress_cb, "scan complete", 1.0)
    return ScanResult(
        scan_id=scan.id,
        clips_found=len(clip_ids),
        categories_run=total - len(errors),
        errors=errors,
    )
