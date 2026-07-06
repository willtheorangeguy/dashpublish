"""Video listing."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from dashpublish.api.deps import get_db_path
from dashpublish.db import repo
from dashpublish.db.engine import session_scope
from dashpublish.db.schemas import VideoOut

router = APIRouter(prefix="/videos", tags=["videos"])


@router.get("", response_model=list[VideoOut])
def list_videos(db_path: str = Depends(get_db_path)) -> list[VideoOut]:
    with session_scope(db_path) as session:
        return [VideoOut.model_validate(v) for v in repo.list_videos(session)]


@router.get("/{video_id}", response_model=VideoOut)
def get_video(video_id: int, db_path: str = Depends(get_db_path)) -> VideoOut:
    with session_scope(db_path) as session:
        video = repo.list_videos(session)
        match = next((v for v in video if v.id == video_id), None)
        if match is None:
            raise HTTPException(status_code=404, detail=f"Video {video_id} not found")
        return VideoOut.model_validate(match)
