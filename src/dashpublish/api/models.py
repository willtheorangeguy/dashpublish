"""API-layer response models.

These wrap the DB DTOs/ORM objects to match the exact shapes the React SPA
(Package F) was built against — adding computed/renamed fields (``category_name``,
``duration_s``, ``edl``, ``tags``) without touching :mod:`dashpublish.db.schemas`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

# --- Clips ----------------------------------------------------------------


class ClipApiOut(BaseModel):
    id: int
    video_id: int
    category_id: int | None = None
    category_name: str | None = None
    scan_id: int | None = None
    score: float
    start_s: float
    end_s: float
    duration_s: float
    clip_path: str | None = None
    dedupe_key: str
    starred: bool
    hidden: bool
    user_tags: dict[str, Any] | None = None
    created_at: datetime

    @classmethod
    def from_orm_clip(cls, clip: Any) -> "ClipApiOut":
        category_name = clip.category.name if clip.category is not None else None
        return cls(
            id=clip.id,
            video_id=clip.video_id,
            category_id=clip.category_id,
            category_name=category_name,
            scan_id=clip.scan_id,
            score=clip.score,
            start_s=clip.start_s,
            end_s=clip.end_s,
            duration_s=max(0.0, clip.end_s - clip.start_s),
            clip_path=clip.clip_path,
            dedupe_key=clip.dedupe_key,
            starred=clip.starred,
            hidden=clip.hidden,
            user_tags=clip.user_tags,
            created_at=clip.created_at,
        )


# --- Compilations ---------------------------------------------------------


def _real_edl(edl_json: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the EDL dict only when it is a real plan (has segments).

    The candidate stash (``{"_candidates": {...}}``) written at create time is not
    a renderable EDL, so it is hidden from the ``edl`` field until planning replaces
    it — the SPA treats ``edl != null`` as "a plan exists".
    """
    if isinstance(edl_json, dict) and "segments" in edl_json:
        return edl_json
    return None


class CompilationApiOut(BaseModel):
    id: int
    title: str | None = None
    profile: str
    status: str
    edl: dict[str, Any] | None = None
    output_path: str | None = None
    music_path: str | None = None
    duration_s: float | None = None
    error: str | None = None
    created_at: datetime

    @classmethod
    def from_orm_compilation(cls, comp: Any) -> "CompilationApiOut":
        edl = _real_edl(comp.edl_json)
        duration = None
        if edl is not None:
            duration = sum(
                max(0.0, s.get("trim_end_s", 0) - s.get("trim_start_s", 0))
                for s in edl.get("segments", [])
            )
        return cls(
            id=comp.id,
            title=comp.title,
            profile=comp.profile,
            status=comp.status,
            edl=edl,
            output_path=comp.output_path,
            music_path=comp.music_path,
            duration_s=duration,
            error=comp.error,
            created_at=comp.created_at,
        )


class CompilationCreateIn(BaseModel):
    profile: str = "short"
    clip_ids: list[int] | None = None
    from_selection: str | None = None
    music_path: str | None = None


class CompilationPatchIn(BaseModel):
    edl: dict[str, Any] | None = None
    title: str | None = None
    music_path: str | None = None


# --- Jobs -----------------------------------------------------------------


def _job_status(status: str) -> str:
    """Map the DB job status onto the SPA's vocabulary (``error`` -> ``failed``)."""
    return "failed" if status == "error" else status


class JobApiOut(BaseModel):
    id: int
    type: str
    status: str
    progress: float
    message: str | None = None
    error: str | None = None
    payload_json: dict[str, Any] | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @classmethod
    def from_orm_job(cls, job: Any) -> "JobApiOut":
        done = job.status in ("done", "error")
        return cls(
            id=job.id,
            type=job.type,
            status=_job_status(job.status),
            progress=job.progress,
            message=job.message,
            error=job.error,
            payload_json=job.payload_json,
            created_at=job.created_at,
            started_at=job.created_at,
            finished_at=job.updated_at if done else None,
        )


# --- Scans ----------------------------------------------------------------


class ScanApiOut(BaseModel):
    id: int
    status: str
    clips_found: int
    error: str | None = None
    started_at: datetime
    finished_at: datetime | None = None

    @classmethod
    def from_orm_scan(cls, scan: Any) -> "ScanApiOut":
        return cls(
            id=scan.id,
            status=scan.status,
            clips_found=scan.clips_found,
            error=scan.error,
            started_at=scan.created_at,
            finished_at=scan.finished_at,
        )


# --- Publish records ------------------------------------------------------


class PublishApiOut(BaseModel):
    id: int
    compilation_id: int
    youtube_video_id: str | None = None
    privacy_status: str
    title: str | None = None
    description: str | None = None
    tags: list[str] = []
    uploaded_at: datetime | None = None
    published_at: datetime | None = None
    created_at: datetime

    @classmethod
    def from_record(cls, record: Any) -> "PublishApiOut":
        return cls(
            id=record.id,
            compilation_id=record.compilation_id,
            youtube_video_id=record.youtube_video_id,
            privacy_status=record.privacy_status,
            title=record.title,
            description=record.description,
            tags=list(record.tags_json or []),
            uploaded_at=record.uploaded_at,
            published_at=record.published_at,
            created_at=record.created_at,
        )


# --- Metadata & settings --------------------------------------------------


class MetadataApiOut(BaseModel):
    title: str
    description: str
    tags: list[str] = []


class SettingsApiOut(BaseModel):
    footage_dir: str
    embeddings_backend: str
    llm_provider: str
    llm_model: str
    ollama_url: str
    youtube_authenticated: bool


class SettingsPatchIn(BaseModel):
    footage_dir: str | None = None
    embeddings_backend: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    ollama_url: str | None = None
