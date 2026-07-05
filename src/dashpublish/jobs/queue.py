"""DB-backed job queue (single-worker assumption).

The worker/tasks live in Package E; this module only manages the ``jobs`` table.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from dashpublish.db.models import Job, utcnow
from dashpublish.db.schemas import JobOut

# Recognized job types.
JOB_TYPES: list[str] = ["index", "scan", "compile", "upload", "publish"]


def enqueue(session: Session, type: str, payload: dict[str, Any] | None = None) -> JobOut:
    """Add a queued job and return its DTO."""
    job = Job(type=type, payload_json=payload or {}, status="queued", progress=0.0)
    session.add(job)
    session.flush()
    return JobOut.model_validate(job)


def claim_next(session: Session) -> Job | None:
    """Claim the oldest queued job, transitioning it to ``running``.

    Returns the ORM :class:`Job` (or ``None`` if the queue is empty). Single-worker
    assumption: no row locking beyond the surrounding transaction.
    """
    job = session.scalar(
        select(Job).where(Job.status == "queued").order_by(Job.id.asc()).limit(1)
    )
    if job is None:
        return None
    job.status = "running"
    job.updated_at = utcnow()
    session.flush()
    return job


def update_progress(
    session: Session,
    job_id: int,
    progress: float,
    message: str | None = None,
) -> Job | None:
    """Update a running job's progress (0.0–1.0) and optional status message."""
    job = session.get(Job, job_id)
    if job is None:
        return None
    job.progress = progress
    if message is not None:
        job.message = message
    job.updated_at = utcnow()
    session.flush()
    return job


def finish(session: Session, job_id: int, error: str | None = None) -> Job | None:
    """Mark a job done (or ``error`` if a message is given)."""
    job = session.get(Job, job_id)
    if job is None:
        return None
    if error is None:
        job.status = "done"
        job.progress = 1.0
    else:
        job.status = "error"
        job.error = error
    job.updated_at = utcnow()
    session.flush()
    return job


def get_job(session: Session, job_id: int) -> Job | None:
    return session.get(Job, job_id)


def list_jobs(session: Session, status: str | None = None) -> list[Job]:
    stmt = select(Job).order_by(Job.id.desc())
    if status is not None:
        stmt = stmt.where(Job.status == status)
    return list(session.scalars(stmt))
