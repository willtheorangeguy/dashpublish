"""Tests for dashpublish.ingest — discovery, Tesla grouping, registration."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from dashpublish.db import repo
from dashpublish.ingest.discovery import discover_videos, parse_generic_timestamp
from dashpublish.ingest.register import content_hash, register_footage
from dashpublish.ingest.tesla import (
    group_tesla_events,
    parse_tesla_filename,
    preferred_camera_paths,
)

CAMS = ("front", "back", "left_repeater", "right_repeater")


def _touch(path: Path, payload: bytes = b"\x00fakevideo") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


@pytest.fixture()
def footage_tree(tmp_path: Path) -> Path:
    """Tesla SavedClips (4 cams x 2 events) plus generic files."""
    root = tmp_path / "footage"
    ev1 = root / "TeslaCam" / "SavedClips" / "2024-01-15_14-30-05"
    ev2 = root / "TeslaCam" / "SentryClips" / "2024-02-20_08-15-40"
    for cam in CAMS:
        _touch(ev1 / f"2024-01-15_14-30-05-{cam}.mp4", payload=b"ev1" + cam.encode())
        _touch(ev2 / f"2024-02-20_08-15-40-{cam}.mp4", payload=b"ev2" + cam.encode())
    _touch(root / "gopro" / "ride_2023-07-04_16-20-30.MP4", payload=b"gopro")
    _touch(root / "gopro" / "random_clip.mov", payload=b"randomclip")
    _touch(root / "notes.txt", payload=b"not a video")
    return root


# --- tesla.py ----------------------------------------------------------------
def test_parse_tesla_filename():
    parsed = parse_tesla_filename(Path("2024-01-15_14-30-05-front.mp4"))
    assert parsed is not None
    assert parsed.camera == "front"
    assert parsed.timestamp == "2024-01-15_14-30-05"
    assert parsed.recorded_at == datetime(2024, 1, 15, 14, 30, 5)


def test_parse_tesla_filename_rejects_non_tesla():
    assert parse_tesla_filename(Path("ride_2023-07-04_16-20-30.mp4")) is None
    assert parse_tesla_filename(Path("2024-01-15_14-30-05-front.txt")) is None
    assert parse_tesla_filename(Path("2024-13-99_14-30-05-front.mp4")) is None


def test_group_tesla_events_by_timestamp_and_dir(tmp_path: Path):
    d1 = tmp_path / "SavedClips" / "e1"
    d2 = tmp_path / "SavedClips" / "e2"
    files = [
        _touch(d1 / "2024-01-15_14-30-05-front.mp4"),
        _touch(d1 / "2024-01-15_14-30-05-back.mp4"),
        # Same timestamp, different directory -> distinct event.
        _touch(d2 / "2024-01-15_14-30-05-front.mp4"),
    ]
    events = group_tesla_events(files)
    assert len(events) == 2
    sizes = sorted(len(v) for v in events.values())
    assert sizes == [1, 2]


def test_preferred_camera_paths_front_only():
    files = [Path(f"2024-01-15_14-30-05-{cam}.mp4") for cam in CAMS]
    assert preferred_camera_paths(files) == [Path("2024-01-15_14-30-05-front.mp4")]


def test_preferred_camera_paths_no_front_returns_all():
    files = [
        Path("2024-01-15_14-30-05-back.mp4"),
        Path("2024-01-15_14-30-05-left_repeater.mp4"),
    ]
    assert preferred_camera_paths(files) == files


# --- discovery.py --------------------------------------------------------------
def test_parse_generic_timestamp_variants():
    assert parse_generic_timestamp("ride_2023-07-04_16-20-30.mp4") == datetime(
        2023, 7, 4, 16, 20, 30
    )
    assert parse_generic_timestamp("2023_07_04 16.20.mp4") == datetime(
        2023, 7, 4, 16, 20, 0
    )
    assert parse_generic_timestamp("no_timestamp_here.mp4") is None
    assert parse_generic_timestamp("9999-99-99_99-99-99.mp4") is None


def test_discover_missing_dir_returns_empty(tmp_path: Path):
    assert discover_videos(tmp_path / "nope") == []


def test_discover_full_tree(footage_tree: Path):
    discovered = discover_videos(footage_tree)
    # 8 Tesla files + 2 generic; notes.txt excluded.
    assert len(discovered) == 10

    tesla = [d for d in discovered if d.source_type == "tesla_event"]
    generic = [d for d in discovered if d.source_type == "generic"]
    assert len(tesla) == 8
    assert len(generic) == 2

    # Two distinct events, four cameras each.
    event_ids = {d.event_id for d in tesla}
    assert len(event_ids) == 2
    for eid in event_ids:
        members = [d for d in tesla if d.event_id == eid]
        assert {m.camera for m in members} == set(CAMS)

    # recorded_at parsed from Tesla filenames.
    ev1 = [d for d in tesla if "2024-01-15_14-30-05" in (d.event_id or "")]
    assert all(d.recorded_at == datetime(2024, 1, 15, 14, 30, 5) for d in ev1)

    # Generic: parseable name gets its filename timestamp, other gets mtime.
    by_name = {d.path.name.lower(): d for d in generic}
    assert by_name["ride_2023-07-04_16-20-30.mp4"].recorded_at == datetime(
        2023, 7, 4, 16, 20, 30
    )
    assert by_name["random_clip.mov"].recorded_at is not None  # mtime fallback
    assert all(d.camera == "generic" and d.event_id is None for d in generic)
    assert all(d.size_bytes > 0 for d in discovered)


def test_discover_case_insensitive_extensions(tmp_path: Path):
    _touch(tmp_path / "A.MP4")
    _touch(tmp_path / "b.MoV")
    _touch(tmp_path / "c.avi")
    assert len(discover_videos(tmp_path)) == 2


# --- register.py ---------------------------------------------------------------
def test_content_hash_depends_on_bytes(tmp_path: Path):
    a = _touch(tmp_path / "a.mp4", payload=b"aaa")
    b = _touch(tmp_path / "b.mp4", payload=b"bbb")
    c = _touch(tmp_path / "c.mp4", payload=b"aaa")
    assert content_hash(a) == content_hash(c)
    assert content_hash(a) != content_hash(b)
    assert content_hash(tmp_path / "missing.mp4") is None


def test_register_footage_prefers_front_and_is_idempotent(session, footage_tree: Path):
    result = register_footage(session, footage_tree)
    # 2 events x 1 front cam + 2 generic = 4 rows.
    assert result.new == 4
    assert result.seen == 0
    assert result.total == 4

    videos = repo.list_videos(session)
    assert len(videos) == 4
    tesla_rows = [v for v in videos if v.source_type == "tesla_event"]
    assert len(tesla_rows) == 2
    assert all(v.camera == "front" for v in tesla_rows)
    assert all(v.event_id for v in tesla_rows)
    assert all(v.content_hash for v in videos)
    assert all(v.recorded_at is not None for v in videos)

    # Second run: nothing new.
    again = register_footage(session, footage_tree)
    assert again.new == 0
    assert again.seen == 4
    assert again.total == 4
    assert len(repo.list_videos(session)) == 4


def test_register_footage_no_front_registers_all_cams(session, tmp_path: Path):
    event = tmp_path / "SavedClips" / "2024-03-01_10-00-00"
    _touch(event / "2024-03-01_10-00-00-back.mp4")
    _touch(event / "2024-03-01_10-00-00-left_repeater.mp4")
    result = register_footage(session, tmp_path)
    assert result.new == 2
    cams = {v.camera for v in repo.list_videos(session)}
    assert cams == {"back", "left_repeater"}
