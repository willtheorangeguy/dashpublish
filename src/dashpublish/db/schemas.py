"""Pydantic DTOs mirroring the ORM models, for API/CLI use.

``*Out`` DTOs are read models (``from_attributes=True`` so they build from ORM objects).
``*In`` / ``*Create`` / ``*Patch`` DTOs are write/update payloads with optional fields.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

SourceType = Literal["tesla_event", "generic"]
ScanStatus = Literal["running", "done", "error", "partial"]
CompilationProfile = Literal["short", "long"]
CompilationStatus = Literal[
    "draft", "planning", "rendering", "rendered", "uploaded", "published", "failed"
]
JobType = Literal["index", "scan", "compile", "upload", "publish"]
JobStatus = Literal["queued", "running", "done", "error"]
PrivacyStatus = Literal["private", "unlisted", "public"]
ClipSort = Literal["score", "recent", "start"]


class _OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Videos ---------------------------------------------------------------
class VideoOut(_OrmModel):
    id: int
    path: str
    camera: str | None = None
    source_type: SourceType = "generic"
    event_id: str | None = None
    duration_s: float | None = None
    content_hash: str | None = None
    recorded_at: datetime | None = None
    indexed_at: datetime | None = None
    created_at: datetime


# --- Categories -----------------------------------------------------------
class CategoryOut(_OrmModel):
    id: int
    name: str
    query_text: str
    threshold: float
    save_top: int
    rerank: bool
    enabled: bool
    is_builtin: bool
    created_at: datetime


class CategoryIn(BaseModel):
    name: str
    query_text: str
    threshold: float = 0.5
    save_top: int = 3
    rerank: bool = True
    enabled: bool = True


# --- Clips ----------------------------------------------------------------
class ClipOut(_OrmModel):
    id: int
    video_id: int
    category_id: int | None = None
    scan_id: int | None = None
    score: float
    start_s: float
    end_s: float
    clip_path: str | None = None
    dedupe_key: str
    starred: bool
    hidden: bool
    user_tags: dict[str, Any] | None = None
    created_at: datetime


class ClipPatch(BaseModel):
    starred: bool | None = None
    hidden: bool | None = None
    user_tags: dict[str, Any] | None = None


# --- Scans ----------------------------------------------------------------
class ScanOut(_OrmModel):
    id: int
    status: ScanStatus
    params: dict[str, Any] | None = None
    clips_found: int
    error: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


# --- Compilations ---------------------------------------------------------
class CompilationOut(_OrmModel):
    id: int
    profile: CompilationProfile
    status: CompilationStatus
    title: str | None = None
    edl_json: dict[str, Any] | None = None
    output_path: str | None = None
    music_path: str | None = None
    error: str | None = None
    created_at: datetime


class CompilationCreate(BaseModel):
    profile: CompilationProfile = "short"
    title: str | None = None
    music_path: str | None = None


class CompilationClipOut(_OrmModel):
    id: int
    compilation_id: int
    clip_id: int
    order_index: int
    trim_start: float | None = None
    trim_end: float | None = None


# --- Publish records ------------------------------------------------------
class PublishRecordOut(_OrmModel):
    id: int
    compilation_id: int
    youtube_video_id: str | None = None
    privacy_status: PrivacyStatus
    title: str | None = None
    description: str | None = None
    tags_json: list[str] | None = None
    uploaded_at: datetime | None = None
    published_at: datetime | None = None
    created_at: datetime


# --- Jobs -----------------------------------------------------------------
class JobOut(_OrmModel):
    id: int
    type: JobType
    payload_json: dict[str, Any] | None = None
    status: JobStatus
    progress: float
    message: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


# --- Settings -------------------------------------------------------------
class SettingOut(_OrmModel):
    key: str
    value: Any | None = None
    updated_at: datetime


# --- Search (used by package B) -------------------------------------------
class SearchMatch(BaseModel):
    """A single ranked match from sentrysearch."""

    score: float
    source_file: str
    start_s: float
    end_s: float
    saved_clip_path: str | None = None
