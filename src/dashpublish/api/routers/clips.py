"""Clip listing, patching, streaming, and thumbnails."""

from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from starlette.responses import FileResponse, Response

from dashpublish.api.deps import get_db_path, get_paths
from dashpublish.api.models import ClipApiOut
from dashpublish.api.streaming import range_file_response
from dashpublish.compile.render import resolve_ffmpeg
from dashpublish.db import repo
from dashpublish.db.engine import session_scope
from dashpublish.db.schemas import ClipPatch

router = APIRouter(prefix="/clips", tags=["clips"])

# Frontend sends the SPA sort vocabulary; map onto repo.list_clips values.
_SORT_MAP = {"score": "score", "newest": "recent", "recent": "recent", "start": "start"}


@router.get("", response_model=list[ClipApiOut])
def list_clips(
    request: Request,
    category: str | None = None,
    starred: bool | None = None,
    hidden: bool | None = None,
    video_id: int | None = None,
    min_score: float | None = None,
    sort: str = Query("score"),
    db_path: str = Depends(get_db_path),
) -> list[ClipApiOut]:
    with session_scope(db_path) as session:
        clips = repo.list_clips(
            session,
            category=category,
            starred=starred,
            hidden=hidden,
            video_id=video_id,
            min_score=min_score,
            sort=_SORT_MAP.get(sort, "score"),
        )
        return [ClipApiOut.from_orm_clip(c) for c in clips]


@router.patch("/{clip_id}", response_model=ClipApiOut)
def patch_clip(
    clip_id: int, patch: ClipPatch, db_path: str = Depends(get_db_path)
) -> ClipApiOut:
    with session_scope(db_path) as session:
        clip = repo.patch_clip(session, clip_id, patch)
        if clip is None:
            raise HTTPException(status_code=404, detail=f"Clip {clip_id} not found")
        return ClipApiOut.from_orm_clip(clip)


@router.get("/{clip_id}/stream")
def stream_clip(
    clip_id: int,
    range: str | None = Header(default=None),
    db_path: str = Depends(get_db_path),
) -> Response:
    with session_scope(db_path) as session:
        clip = repo.get_clip(session, clip_id)
        clip_path = clip.clip_path if clip is not None else None
    if not clip_path or not Path(clip_path).exists():
        raise HTTPException(status_code=404, detail="Clip file not available")
    return range_file_response(clip_path, range)


@router.get("/{clip_id}/thumb")
def clip_thumb(
    clip_id: int,
    db_path: str = Depends(get_db_path),
    paths=Depends(get_paths),
) -> Response:
    with session_scope(db_path) as session:
        clip = repo.get_clip(session, clip_id)
        if clip is None or not clip.clip_path:
            raise HTTPException(status_code=404, detail="Clip not found")
        clip_path = clip.clip_path
        midpoint = max(0.0, (clip.end_s - clip.start_s) / 2)

    if not Path(clip_path).exists():
        raise HTTPException(status_code=404, detail="Clip file not available")

    thumb_path = Path(paths.thumbs_dir) / f"{clip_id}.jpg"
    if not thumb_path.exists():
        ffmpeg = resolve_ffmpeg()
        if ffmpeg is None:
            raise HTTPException(status_code=404, detail="Thumbnails unavailable (no ffmpeg)")
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        argv = [
            ffmpeg, "-hide_banner", "-y",
            "-ss", f"{midpoint:.3f}",
            "-i", str(clip_path),
            "-frames:v", "1",
            "-vf", "scale=480:-1",
            str(thumb_path),
        ]
        try:
            proc = subprocess.run(argv, capture_output=True, text=True)
        except OSError:
            raise HTTPException(status_code=404, detail="Thumbnail extraction failed") from None
        if proc.returncode != 0 or not thumb_path.exists():
            raise HTTPException(status_code=404, detail="Thumbnail extraction failed")

    return FileResponse(thumb_path, media_type="image/jpeg")
