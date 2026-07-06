"""Worker + task tests: synchronous draining, failure isolation, thread lifecycle."""

from __future__ import annotations

import time

import pytest

from dashpublish.api.app import _ensure_schema
from dashpublish.config import load_config, reset_config
from dashpublish.db.engine import session_scope
from dashpublish.jobs import queue
from dashpublish.jobs.tasks import run_pending_jobs
from dashpublish.jobs.worker import Worker
from dashpublish.paths import resolve_paths


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    cfg_path = tmp_path / "dashpublish.toml"
    cfg_path.write_text(f'[general]\ndata_dir = "{data_dir.as_posix()}"\n')
    monkeypatch.setenv("DASHPUBLISH_FAKE", "1")
    monkeypatch.setenv("DASHPUBLISH_NO_WORKER", "1")
    monkeypatch.setenv("DASHPUBLISH_CONFIG", str(cfg_path))
    reset_config()
    cfg = load_config()
    path = str(resolve_paths(cfg).db_path)
    _ensure_schema(path)  # tables + seeded categories
    yield path
    reset_config()


def _enqueue(db_path, jtype, payload=None):
    with session_scope(db_path) as session:
        return queue.enqueue(session, jtype, payload or {}).id


def _job(db_path, job_id):
    with session_scope(db_path) as session:
        return queue.get_job(session, job_id)


def test_run_pending_jobs_processes_scan(db_path):
    job_id = _enqueue(db_path, "scan")
    processed = run_pending_jobs(db_path)
    assert processed == 1

    job = _job(db_path, job_id)
    assert job.status == "done"
    assert job.progress == 1.0
    assert job.message  # progress messages were recorded


def test_task_exception_marks_failed_and_survives(db_path):
    bad_id = _enqueue(db_path, "compile", {"action": "bogus"})
    good_id = _enqueue(db_path, "scan")

    # A raising task must not stop the drain of subsequent jobs.
    processed = run_pending_jobs(db_path)
    assert processed == 2

    bad = _job(db_path, bad_id)
    assert bad.status == "error"
    assert bad.error and "action" in bad.error
    assert _job(db_path, good_id).status == "done"


def test_early_compile_failure_unsticks_compilation(db_path, monkeypatch):
    """A compile task failing before its own handler (e.g. provider setup) must
    still flip the compilation out of its transient status."""
    from dashpublish.db import repo
    from dashpublish.jobs import tasks

    with session_scope(db_path) as session:
        comp = repo.create_compilation(session, profile="short", status="planning")
        comp_id = comp.id

    def boom(cfg):
        raise RuntimeError("no API key configured")

    monkeypatch.setattr(tasks, "get_provider", boom)
    job_id = _enqueue(db_path, "compile", {"action": "plan", "compilation_id": comp_id})
    run_pending_jobs(db_path)

    assert _job(db_path, job_id).status == "error"
    with session_scope(db_path) as session:
        comp = repo.get_compilation(session, comp_id)
        assert comp.status == "failed"
        assert "no API key" in comp.error


def test_worker_thread_lifecycle(db_path):
    worker = Worker(db_path, poll_interval=0.05).start()
    try:
        job_id = _enqueue(db_path, "scan")
        deadline = time.time() + 5.0
        while time.time() < deadline:
            if _job(db_path, job_id).status in ("done", "error"):
                break
            time.sleep(0.02)
        job = _job(db_path, job_id)
        assert job.status == "done"
        assert worker._thread is not None and worker._thread.is_alive()
    finally:
        worker.stop()
    assert worker._thread is None
