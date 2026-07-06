"""Tests for the watch daemon (:mod:`dashpublish.watch.daemon`)."""

from __future__ import annotations

import threading

import pytest

from dashpublish.config import load_config, reset_config
from dashpublish.db.engine import session_scope, upgrade_db
from dashpublish.ingest import register_footage
from dashpublish.jobs import queue
from dashpublish.paths import resolve_paths
from dashpublish.watch import daemon as daemon_mod
from dashpublish.watch.daemon import SETTLE_S, watch_loop


@pytest.fixture()
def env(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    footage_dir = tmp_path / "footage"
    footage_dir.mkdir()
    cfg_path = tmp_path / "dashpublish.toml"
    cfg_path.write_text(
        f'[general]\nfootage_dir = "{footage_dir.as_posix()}"\n'
        f'data_dir = "{data_dir.as_posix()}"\n'
    )
    monkeypatch.setenv("DASHPUBLISH_FAKE", "1")
    monkeypatch.setenv("DASHPUBLISH_CONFIG", str(cfg_path))
    reset_config()
    cfg = load_config()
    paths = resolve_paths(cfg)
    upgrade_db(str(paths.db_path))
    db_path = str(paths.db_path)

    # The settle pass really sleeps SETTLE_S seconds; make tests instant.
    monkeypatch.setattr(daemon_mod.time, "sleep", lambda s: None)

    yield cfg, db_path, footage_dir
    reset_config()


def _job_types(db_path) -> list[str]:
    with session_scope(db_path) as session:
        return [j.type for j in queue.list_jobs(session)]


def test_watch_loop_enqueues_index_and_scan_on_new_footage(env):
    cfg, db_path, footage_dir = env
    (footage_dir / "clip1.mp4").write_bytes(b"video-bytes")

    watch_loop(cfg, db_path, once=True, enqueue_only=True)

    types = _job_types(db_path)
    assert sorted(types) == ["index", "scan"]
    with session_scope(db_path) as session:
        for job in queue.list_jobs(session):
            assert job.status == "queued"  # enqueue_only leaves them queued


def test_watch_loop_no_jobs_when_nothing_new(env):
    cfg, db_path, footage_dir = env
    (footage_dir / "clip1.mp4").write_bytes(b"video-bytes")

    # Register once "out of band" so the daemon sees nothing new on its tick.
    with session_scope(db_path) as session:
        register_footage(session, footage_dir)

    watch_loop(cfg, db_path, once=True, enqueue_only=True)

    assert _job_types(db_path) == []


def test_watch_loop_settle_pass_reregisters_before_enqueueing(env, monkeypatch):
    cfg, db_path, footage_dir = env
    (footage_dir / "clip1.mp4").write_bytes(b"video-bytes")

    calls: list[float] = []
    monkeypatch.setattr(daemon_mod.time, "sleep", lambda s: calls.append(s))

    watch_loop(cfg, db_path, once=True, enqueue_only=True)

    assert calls == [SETTLE_S]
    assert sorted(_job_types(db_path)) == ["index", "scan"]


def test_watch_loop_drains_jobs_when_not_enqueue_only(env):
    cfg, db_path, footage_dir = env
    (footage_dir / "clip1.mp4").write_bytes(b"video-bytes")

    watch_loop(cfg, db_path, once=True, enqueue_only=False)

    with session_scope(db_path) as session:
        jobs = queue.list_jobs(session)
    assert len(jobs) == 2
    assert all(j.status == "done" for j in jobs)


def test_watch_loop_stops_on_stop_event_between_ticks(env):
    cfg, db_path, footage_dir = env
    stop_event = threading.Event()
    stop_event.set()  # fires immediately after the first tick's interval wait

    (footage_dir / "clip1.mp4").write_bytes(b"video-bytes")
    watch_loop(
        cfg, db_path, interval_s=0.01, once=False, enqueue_only=True, stop_event=stop_event
    )

    # One tick still ran before the stop event was observed.
    assert sorted(_job_types(db_path)) == ["index", "scan"]


def test_watch_loop_requires_footage_dir(tmp_path, monkeypatch):
    cfg_path = tmp_path / "dashpublish.toml"
    cfg_path.write_text(f'[general]\ndata_dir = "{(tmp_path / "data").as_posix()}"\n')
    monkeypatch.setenv("DASHPUBLISH_FAKE", "1")
    monkeypatch.setenv("DASHPUBLISH_CONFIG", str(cfg_path))
    reset_config()
    cfg = load_config()
    paths = resolve_paths(cfg)
    upgrade_db(str(paths.db_path))

    with pytest.raises(ValueError):
        watch_loop(cfg, str(paths.db_path), once=True)
    reset_config()
