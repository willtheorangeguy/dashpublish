"""Typed data-access helpers.

Every function takes a live :class:`~sqlalchemy.orm.Session` as its first argument and
returns ORM objects (from :mod:`dashpublish.db.models`). Callers are responsible for the
transaction boundary (use :func:`dashpublish.db.engine.session_scope`). Functions flush
so that generated primary keys are populated, but do not commit.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from dashpublish.db.models import (
    Category,
    Clip,
    Compilation,
    CompilationClip,
    PublishRecord,
    Scan,
    Setting,
    Video,
    utcnow,
)
from dashpublish.db.schemas import CategoryIn, ClipPatch

# --- Default detection categories (seeded on init) ------------------------
DEFAULT_CATEGORIES: list[dict[str, Any]] = [
    {
        "name": "overtaking",
        "query_text": "a car overtaking or passing another vehicle on the road",
    },
    {
        "name": "high-speed",
        "query_text": "driving at high speed, fast motion on a highway or open road",
    },
    {
        "name": "cut-off",
        "query_text": "another vehicle cutting off or merging dangerously in front of the car",
    },
    {
        "name": "near-miss",
        "query_text": "a near miss or close call narrowly avoiding a collision",
    },
    {
        "name": "tailgating",
        "query_text": "a vehicle tailgating or following too closely behind",
    },
    {
        "name": "red-light",
        "query_text": "a vehicle running a red light or ignoring a traffic signal",
    },
    {
        "name": "crash",
        "query_text": "a car crash, collision, or accident on the road",
    },
    {
        "name": "funny",
        "query_text": "a funny, unusual, or amusing moment caught while driving",
    },
]


# =========================================================================
# Videos
# =========================================================================
def upsert_video(session: Session, path: str, **fields: Any) -> Video:
    """Insert or update a video keyed on its unique ``path``."""
    video = session.scalar(select(Video).where(Video.path == path))
    if video is None:
        video = Video(path=path, **fields)
        session.add(video)
    else:
        for key, value in fields.items():
            setattr(video, key, value)
    session.flush()
    return video


def list_videos(session: Session) -> list[Video]:
    return list(session.scalars(select(Video).order_by(Video.id)))


def get_unindexed_videos(session: Session) -> list[Video]:
    """Videos not yet embedded/indexed (``indexed_at IS NULL``)."""
    return list(
        session.scalars(
            select(Video).where(Video.indexed_at.is_(None)).order_by(Video.id)
        )
    )


def mark_indexed(
    session: Session, video_id: int, indexed_at: datetime | None = None
) -> Video | None:
    video = session.get(Video, video_id)
    if video is None:
        return None
    video.indexed_at = indexed_at or utcnow()
    session.flush()
    return video


# =========================================================================
# Categories
# =========================================================================
def list_categories(session: Session, enabled_only: bool = False) -> list[Category]:
    stmt = select(Category).order_by(Category.id)
    if enabled_only:
        stmt = stmt.where(Category.enabled.is_(True))
    return list(session.scalars(stmt))


def get_category(session: Session, category_id: int) -> Category | None:
    return session.get(Category, category_id)


def get_category_by_name(session: Session, name: str) -> Category | None:
    return session.scalar(select(Category).where(Category.name == name))


def create_category(session: Session, data: CategoryIn) -> Category:
    category = Category(
        name=data.name,
        query_text=data.query_text,
        threshold=data.threshold,
        save_top=data.save_top,
        rerank=data.rerank,
        enabled=data.enabled,
        is_builtin=False,
    )
    session.add(category)
    session.flush()
    return category


def update_category(session: Session, category_id: int, **fields: Any) -> Category | None:
    category = session.get(Category, category_id)
    if category is None:
        return None
    for key, value in fields.items():
        setattr(category, key, value)
    session.flush()
    return category


def delete_category(session: Session, category_id: int) -> bool:
    category = session.get(Category, category_id)
    if category is None:
        return False
    session.delete(category)
    session.flush()
    return True


def seed_default_categories(session: Session) -> list[Category]:
    """Seed the built-in detection categories. Idempotent (keyed on name)."""
    seeded: list[Category] = []
    for spec in DEFAULT_CATEGORIES:
        existing = get_category_by_name(session, spec["name"])
        if existing is not None:
            seeded.append(existing)
            continue
        category = Category(
            name=spec["name"],
            query_text=spec["query_text"],
            threshold=0.5,
            save_top=3,
            rerank=True,
            enabled=True,
            is_builtin=True,
        )
        session.add(category)
        seeded.append(category)
    session.flush()
    return seeded


# =========================================================================
# Clips
# =========================================================================
def make_dedupe_key(video_id: int, start_s: float, window: int) -> str:
    """dedupe_key groups clips from the same video into time buckets."""
    bucket = int(start_s // window) if window > 0 else int(start_s)
    return f"{video_id}:{bucket}"


def _add_also_tag(clip: Clip, category_name: str | None) -> None:
    if not category_name:
        return
    tags = dict(clip.user_tags or {})
    also = list(tags.get("also", []))
    if category_name not in also:
        also.append(category_name)
    tags["also"] = also
    clip.user_tags = tags


def upsert_clip_deduped(
    session: Session,
    *,
    video_id: int,
    score: float,
    start_s: float,
    end_s: float,
    window: int,
    category_id: int | None = None,
    category_name: str | None = None,
    clip_path: str | None = None,
    scan_id: int | None = None,
) -> Clip:
    """Insert a clip, deduplicating on the (video, time-bucket) key.

    If a clip already occupies the bucket, the higher-scoring clip wins and the losing
    clip's category name is merged into the winner's ``user_tags["also"]`` list.
    """
    dedupe_key = make_dedupe_key(video_id, start_s, window)
    existing = session.scalar(select(Clip).where(Clip.dedupe_key == dedupe_key))

    if existing is None:
        clip = Clip(
            video_id=video_id,
            category_id=category_id,
            scan_id=scan_id,
            score=score,
            start_s=start_s,
            end_s=end_s,
            clip_path=clip_path,
            dedupe_key=dedupe_key,
        )
        session.add(clip)
        session.flush()
        return clip

    if score > existing.score:
        # New clip wins; demote the old category into "also".
        losing_name = category_name_for(session, existing.category_id)
        existing.score = score
        existing.start_s = start_s
        existing.end_s = end_s
        existing.category_id = category_id
        if clip_path:
            existing.clip_path = clip_path
        if scan_id is not None:
            existing.scan_id = scan_id
        _add_also_tag(existing, losing_name)
    else:
        # Existing clip stays primary; record the new category as secondary.
        _add_also_tag(existing, category_name)
    session.flush()
    return existing


def category_name_for(session: Session, category_id: int | None) -> str | None:
    if category_id is None:
        return None
    category = session.get(Category, category_id)
    return category.name if category else None


def list_clips(
    session: Session,
    *,
    category: str | None = None,
    starred: bool | None = None,
    hidden: bool | None = None,
    video_id: int | None = None,
    min_score: float | None = None,
    sort: str = "score",
) -> list[Clip]:
    stmt = select(Clip)
    if category is not None:
        stmt = stmt.join(Category, Clip.category_id == Category.id).where(
            Category.name == category
        )
    if starred is not None:
        stmt = stmt.where(Clip.starred.is_(starred))
    if hidden is not None:
        stmt = stmt.where(Clip.hidden.is_(hidden))
    if video_id is not None:
        stmt = stmt.where(Clip.video_id == video_id)
    if min_score is not None:
        stmt = stmt.where(Clip.score >= min_score)

    if sort == "recent":
        stmt = stmt.order_by(Clip.created_at.desc(), Clip.id.desc())
    elif sort == "start":
        stmt = stmt.order_by(Clip.start_s.asc(), Clip.id.asc())
    else:  # "score"
        stmt = stmt.order_by(Clip.score.desc(), Clip.id.asc())

    return list(session.scalars(stmt))


def get_clip(session: Session, clip_id: int) -> Clip | None:
    return session.get(Clip, clip_id)


def patch_clip(session: Session, clip_id: int, patch: ClipPatch) -> Clip | None:
    clip = session.get(Clip, clip_id)
    if clip is None:
        return None
    data = patch.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(clip, key, value)
    session.flush()
    return clip


# =========================================================================
# Scans
# =========================================================================
def create_scan(session: Session, params: dict[str, Any] | None = None) -> Scan:
    scan = Scan(status="running", params=params, clips_found=0)
    session.add(scan)
    session.flush()
    return scan


def finish_scan(
    session: Session,
    scan_id: int,
    *,
    status: str = "done",
    clips_found: int | None = None,
    error: str | None = None,
) -> Scan | None:
    scan = session.get(Scan, scan_id)
    if scan is None:
        return None
    scan.status = status
    if clips_found is not None:
        scan.clips_found = clips_found
    scan.error = error
    scan.finished_at = utcnow()
    session.flush()
    return scan


def list_scans(session: Session) -> list[Scan]:
    return list(session.scalars(select(Scan).order_by(Scan.id.desc())))


# =========================================================================
# Compilations
# =========================================================================
def create_compilation(
    session: Session,
    *,
    profile: str = "short",
    title: str | None = None,
    music_path: str | None = None,
    status: str = "draft",
) -> Compilation:
    comp = Compilation(
        profile=profile, title=title, music_path=music_path, status=status
    )
    session.add(comp)
    session.flush()
    return comp


def update_compilation(
    session: Session, compilation_id: int, **fields: Any
) -> Compilation | None:
    comp = session.get(Compilation, compilation_id)
    if comp is None:
        return None
    for key, value in fields.items():
        setattr(comp, key, value)
    session.flush()
    return comp


def list_compilations(session: Session) -> list[Compilation]:
    return list(session.scalars(select(Compilation).order_by(Compilation.id.desc())))


def get_compilation(session: Session, compilation_id: int) -> Compilation | None:
    return session.get(Compilation, compilation_id)


def add_compilation_clips(
    session: Session,
    compilation_id: int,
    items: Sequence[dict[str, Any]],
) -> list[CompilationClip]:
    """Append ordered segments to a compilation.

    Each item: ``{clip_id, order_index?, trim_start?, trim_end?}``. When ``order_index``
    is omitted, segments are appended after the current max order index.
    """
    existing = list(
        session.scalars(
            select(CompilationClip).where(
                CompilationClip.compilation_id == compilation_id
            )
        )
    )
    next_index = max((c.order_index for c in existing), default=-1) + 1

    created: list[CompilationClip] = []
    for item in items:
        order_index = item.get("order_index")
        if order_index is None:
            order_index = next_index
            next_index += 1
        cc = CompilationClip(
            compilation_id=compilation_id,
            clip_id=item["clip_id"],
            order_index=order_index,
            trim_start=item.get("trim_start"),
            trim_end=item.get("trim_end"),
        )
        session.add(cc)
        created.append(cc)
    session.flush()
    return created


def list_compilation_clips(
    session: Session, compilation_id: int
) -> list[CompilationClip]:
    return list(
        session.scalars(
            select(CompilationClip)
            .where(CompilationClip.compilation_id == compilation_id)
            .order_by(CompilationClip.order_index)
        )
    )


# =========================================================================
# Publish records
# =========================================================================
def create_publish_record(
    session: Session,
    *,
    compilation_id: int,
    privacy_status: str = "private",
    title: str | None = None,
    description: str | None = None,
    tags_json: list[str] | None = None,
    youtube_video_id: str | None = None,
) -> PublishRecord:
    record = PublishRecord(
        compilation_id=compilation_id,
        privacy_status=privacy_status,
        title=title,
        description=description,
        tags_json=tags_json,
        youtube_video_id=youtube_video_id,
    )
    session.add(record)
    session.flush()
    return record


def update_publish_record(
    session: Session, record_id: int, **fields: Any
) -> PublishRecord | None:
    record = session.get(PublishRecord, record_id)
    if record is None:
        return None
    for key, value in fields.items():
        setattr(record, key, value)
    session.flush()
    return record


def list_publish_records(
    session: Session, compilation_id: int | None = None
) -> list[PublishRecord]:
    stmt = select(PublishRecord).order_by(PublishRecord.id.desc())
    if compilation_id is not None:
        stmt = stmt.where(PublishRecord.compilation_id == compilation_id)
    return list(session.scalars(stmt))


# =========================================================================
# Settings
# =========================================================================
def get_setting(session: Session, key: str, default: Any = None) -> Any:
    setting = session.get(Setting, key)
    return setting.value if setting is not None else default


def set_setting(session: Session, key: str, value: Any) -> Setting:
    setting = session.get(Setting, key)
    if setting is None:
        setting = Setting(key=key, value=value)
        session.add(setting)
    else:
        setting.value = value
    session.flush()
    return setting


def list_settings(session: Session) -> list[Setting]:
    return list(session.scalars(select(Setting).order_by(Setting.key)))
