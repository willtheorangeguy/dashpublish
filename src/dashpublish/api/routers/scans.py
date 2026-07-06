"""Scan enqueue + listing."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from dashpublish.api.deps import get_db_path
from dashpublish.api.models import JobApiOut, ScanApiOut
from dashpublish.db import repo
from dashpublish.db.engine import session_scope
from dashpublish.jobs import queue

router = APIRouter(tags=["scans"])


@router.post("/scans", response_model=JobApiOut, status_code=202)
def start_scan(db_path: str = Depends(get_db_path)) -> JobApiOut:
    with session_scope(db_path) as session:
        job = queue.enqueue(session, "scan", {})
        job_row = queue.get_job(session, job.id)
        return JobApiOut.from_orm_job(job_row)


@router.get("/scans", response_model=list[ScanApiOut])
def list_scans(db_path: str = Depends(get_db_path)) -> list[ScanApiOut]:
    with session_scope(db_path) as session:
        return [ScanApiOut.from_orm_scan(s) for s in repo.list_scans(session)]
