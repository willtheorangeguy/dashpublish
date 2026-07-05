"""Shared test fakes and factory helpers for all packages.

Import from here in tests to get an in-memory session and cheap object factories.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from dashpublish.db.engine import create_all_for_tests, get_engine
from dashpublish.db.models import (
    Category,
    Clip,
    Compilation,
    Video,
    utcnow,
)
from dashpublish.db.repo import make_dedupe_key
from dashpublish.llm.base import FakeProvider

__all__ = [
    "FakeProvider",
    "make_test_session",
    "make_video",
    "make_category",
    "make_clip",
    "make_compilation",
]


def make_test_session(db_path: str = ":memory:") -> Session:
    """Return a Session against a fresh schema (in-memory sqlite by default)."""
    engine = get_engine(db_path)
    create_all_for_tests(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    return factory()


_video_counter = {"n": 0}


def make_video(session: Session, **kw: Any) -> Video:
    _video_counter["n"] += 1
    n = _video_counter["n"]
    defaults: dict[str, Any] = {
        "path": f"/footage/video_{n}.mp4",
        "source_type": "generic",
        "duration_s": 60.0,
    }
    defaults.update(kw)
    video = Video(**defaults)
    session.add(video)
    session.flush()
    return video


def make_category(session: Session, **kw: Any) -> Category:
    defaults: dict[str, Any] = {
        "name": kw.pop("name", "overtaking"),
        "query_text": "a car overtaking another vehicle",
        "threshold": 0.5,
        "save_top": 3,
        "rerank": True,
        "enabled": True,
        "is_builtin": False,
    }
    defaults.update(kw)
    category = Category(**defaults)
    session.add(category)
    session.flush()
    return category


def make_clip(session: Session, **kw: Any) -> Clip:
    video_id = kw.get("video_id")
    if video_id is None:
        video_id = make_video(session).id
        kw["video_id"] = video_id
    start_s = kw.get("start_s", 1.0)
    window = kw.pop("window", 3)
    defaults: dict[str, Any] = {
        "video_id": video_id,
        "category_id": kw.get("category_id"),
        "score": 0.8,
        "start_s": start_s,
        "end_s": kw.get("end_s", start_s + 5.0),
        "clip_path": None,
        "dedupe_key": make_dedupe_key(video_id, start_s, window),
        "starred": False,
        "hidden": False,
    }
    defaults.update(kw)
    clip = Clip(**defaults)
    session.add(clip)
    session.flush()
    return clip


def make_compilation(session: Session, **kw: Any) -> Compilation:
    defaults: dict[str, Any] = {
        "profile": "short",
        "status": "draft",
        "created_at": utcnow(),
    }
    defaults.update(kw)
    comp = Compilation(**defaults)
    session.add(comp)
    session.flush()
    return comp
