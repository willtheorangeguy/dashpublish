"""Job listing + polling."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from dashpublish.api.deps import get_db_path
from dashpublish.api.models import JobApiOut
from dashpublish.db.engine import session_scope
from dashpublish.jobs import queue

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobApiOut])
def list_jobs(db_path: str = Depends(get_db_path)) -> list[JobApiOut]:
    with session_scope(db_path) as session:
        return [JobApiOut.from_orm_job(j) for j in queue.list_jobs(session)]


@router.get("/{job_id}", response_model=JobApiOut)
def get_job(job_id: int, db_path: str = Depends(get_db_path)) -> JobApiOut:
    with session_scope(db_path) as session:
        job = queue.get_job(session, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        return JobApiOut.from_orm_job(job)
