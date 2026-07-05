"""Tests for dashpublish.jobs.queue."""

from __future__ import annotations

from dashpublish.jobs import queue


def test_enqueue_returns_dto(session):
    job = queue.enqueue(session, "scan", {"category": "overtaking"})
    assert job.id is not None
    assert job.type == "scan"
    assert job.status == "queued"
    assert job.progress == 0.0
    assert job.payload_json == {"category": "overtaking"}


def test_claim_order_oldest_first(session):
    j1 = queue.enqueue(session, "index", {})
    j2 = queue.enqueue(session, "scan", {})

    claimed = queue.claim_next(session)
    assert claimed.id == j1.id
    assert claimed.status == "running"

    claimed2 = queue.claim_next(session)
    assert claimed2.id == j2.id

    assert queue.claim_next(session) is None


def test_update_progress(session):
    job = queue.enqueue(session, "compile", {})
    queue.claim_next(session)
    updated = queue.update_progress(session, job.id, 0.5, "halfway")
    assert updated.progress == 0.5
    assert updated.message == "halfway"


def test_finish_success(session):
    job = queue.enqueue(session, "upload", {})
    queue.claim_next(session)
    finished = queue.finish(session, job.id)
    assert finished.status == "done"
    assert finished.progress == 1.0
    assert finished.error is None


def test_finish_with_error(session):
    job = queue.enqueue(session, "publish", {})
    queue.claim_next(session)
    finished = queue.finish(session, job.id, error="boom")
    assert finished.status == "error"
    assert finished.error == "boom"


def test_list_jobs_and_get(session):
    queue.enqueue(session, "index", {})
    queue.enqueue(session, "scan", {})
    all_jobs = queue.list_jobs(session)
    assert len(all_jobs) == 2
    queued = queue.list_jobs(session, status="queued")
    assert len(queued) == 2
    assert queue.get_job(session, all_jobs[0].id) is not None


def test_job_types_constant():
    assert queue.JOB_TYPES == ["index", "scan", "compile", "upload", "publish"]
