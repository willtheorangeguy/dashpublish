"""SQLAlchemy 2.0 ORM models — the shared data contract for all packages.

Enums are stored as ``String`` columns; the allowed values are documented here and
enforced at the DTO layer (see :mod:`dashpublish.db.schemas`) via ``Literal`` types.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """Timezone-aware UTC now (used for created_at defaults)."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# --- source_type values: "tesla_event" | "generic"
# --- categories: builtin detection queries
# --- clips.dedupe_key: f"{video_id}:{int(start_s // dedupe_window_s)}"
# --- scans.status: "running" | "done" | "error"
# --- compilations.profile: "short" | "long"
# --- compilations.status: draft|planning|rendering|rendered|uploaded|published|failed
# --- jobs.type: index|scan|compile|upload|publish
# --- jobs.status: queued|running|done|error
# --- publish_records.privacy_status: private|unlisted|public


class Video(Base):
    __tablename__ = "videos"
    __table_args__ = (UniqueConstraint("path", name="uq_videos_path"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    path: Mapped[str] = mapped_column(String, nullable=False)
    camera: Mapped[str | None] = mapped_column(String, nullable=True)
    source_type: Mapped[str] = mapped_column(String, nullable=False, default="generic")
    event_id: Mapped[str | None] = mapped_column(String, nullable=True)
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # NULL indexed_at == not yet embedded/indexed by sentrysearch.
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    clips: Mapped[list["Clip"]] = relationship(back_populates="video")


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("name", name="uq_categories_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    threshold: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    save_top: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    rerank: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    clips: Mapped[list["Clip"]] = relationship(back_populates="category")


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String, default="running", nullable=False)
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    clips_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    clips: Mapped[list["Clip"]] = relationship(back_populates="scan")


class Clip(Base):
    __tablename__ = "clips"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_clips_dedupe_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    scan_id: Mapped[int | None] = mapped_column(ForeignKey("scans.id"), nullable=True)
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    start_s: Mapped[float] = mapped_column(Float, nullable=False)
    end_s: Mapped[float] = mapped_column(Float, nullable=False)
    clip_path: Mapped[str | None] = mapped_column(String, nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String, nullable=False)
    starred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    user_tags: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    video: Mapped["Video"] = relationship(back_populates="clips")
    category: Mapped["Category | None"] = relationship(back_populates="clips")
    scan: Mapped["Scan | None"] = relationship(back_populates="clips")


class Compilation(Base):
    __tablename__ = "compilations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile: Mapped[str] = mapped_column(String, nullable=False, default="short")
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft")
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    edl_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_path: Mapped[str | None] = mapped_column(String, nullable=True)
    music_path: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    clips: Mapped[list["CompilationClip"]] = relationship(
        back_populates="compilation",
        order_by="CompilationClip.order_index",
        cascade="all, delete-orphan",
    )
    publish_records: Mapped[list["PublishRecord"]] = relationship(
        back_populates="compilation"
    )


class CompilationClip(Base):
    __tablename__ = "compilation_clips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    compilation_id: Mapped[int] = mapped_column(
        ForeignKey("compilations.id"), nullable=False
    )
    clip_id: Mapped[int] = mapped_column(ForeignKey("clips.id"), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    trim_start: Mapped[float | None] = mapped_column(Float, nullable=True)
    trim_end: Mapped[float | None] = mapped_column(Float, nullable=True)

    compilation: Mapped["Compilation"] = relationship(back_populates="clips")
    clip: Mapped["Clip"] = relationship()


class PublishRecord(Base):
    __tablename__ = "publish_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    compilation_id: Mapped[int] = mapped_column(
        ForeignKey("compilations.id"), nullable=False
    )
    youtube_video_id: Mapped[str | None] = mapped_column(String, nullable=True)
    privacy_status: Mapped[str] = mapped_column(String, default="private", nullable=False)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    compilation: Mapped["Compilation"] = relationship(back_populates="publish_records")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String, nullable=False)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String, default="queued", nullable=False)
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )
