"""In-process background worker: a daemon thread that drains the job queue.

Single-worker assumption (matching :mod:`dashpublish.jobs.queue`). The FastAPI app
starts one on startup (unless ``DASHPUBLISH_NO_WORKER=1``); the CLI ``serve``/``watch``
commands reuse :func:`start_worker`. Tests disable the thread and drive jobs
synchronously via :func:`dashpublish.jobs.tasks.run_pending_jobs`.
"""

from __future__ import annotations

import threading
from pathlib import Path

from dashpublish.db.engine import session_scope
from dashpublish.jobs import queue
from dashpublish.jobs.tasks import run_job
from dashpublish.logging import get_logger

logger = get_logger(__name__)


class Worker:
    """A daemon thread that claims and runs queued jobs one at a time."""

    def __init__(self, db_path: str | Path, poll_interval: float = 1.0) -> None:
        self.db_path = str(db_path)
        self.poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _claim_next_id(self) -> int | None:
        with session_scope(self.db_path) as session:
            job = queue.claim_next(session)
            return job.id if job is not None else None

    def _run_loop(self) -> None:
        logger.info("worker started (db=%s)", self.db_path)
        while not self._stop.is_set():
            try:
                job_id = self._claim_next_id()
            except Exception:  # noqa: BLE001 - keep the worker alive on transient DB errors
                logger.exception("worker failed to claim a job")
                job_id = None

            if job_id is None:
                # Nothing to do; wait (interruptibly) before polling again.
                self._stop.wait(self.poll_interval)
                continue

            try:
                run_job(job_id, self.db_path)
            except Exception:  # noqa: BLE001 - run_job already records errors; belt & braces
                logger.exception("worker crashed while running job %s", job_id)
        logger.info("worker stopped")

    def start(self) -> "Worker":
        if self._thread is not None and self._thread.is_alive():
            return self
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_loop, name="dashpublish-worker", daemon=True
        )
        self._thread.start()
        return self

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
        self._thread = None


def start_worker(db_path: str | Path, poll_interval: float = 1.0) -> Worker:
    """Create and start a :class:`Worker` for ``db_path``."""
    return Worker(db_path, poll_interval=poll_interval).start()
