"""Watch daemon: periodically re-scan the footage directory for new files.

Each tick calls :func:`dashpublish.ingest.register_footage`. If new files were found,
it waits :data:`SETTLE_S` seconds (uploads may still be in progress) and re-registers
once more — a "settle" pass — before enqueuing an ``index`` job followed by a ``scan``
job (the same job types / payload shape used by the API and
:mod:`dashpublish.jobs.tasks`).

Whether this process drains those jobs itself or leaves them queued for another
process is controlled by ``enqueue_only``. The docker-compose ``watch`` service sets
``DASHPUBLISH_NO_WORKER=1`` and shares its database with the ``web`` service, whose
in-process worker (or ``serve``'s worker thread) drains the queue; a standalone
``dashpublish watch`` (no ``serve`` running alongside it) should drain jobs itself.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from dashpublish.config import Config
from dashpublish.db.engine import session_scope
from dashpublish.ingest import register_footage
from dashpublish.jobs import queue
from dashpublish.jobs.tasks import run_pending_jobs
from dashpublish.logging import get_logger

logger = get_logger(__name__)

# How long to wait after first seeing new files before enqueuing processing jobs,
# to avoid racing an in-progress upload (still-being-written files).
SETTLE_S = 30.0


def _default_enqueue_only() -> bool:
    return os.environ.get("DASHPUBLISH_NO_WORKER") == "1"


def _tick(cfg: Config, db_path: str, *, footage_dir: Path, enqueue_only: bool) -> int:
    """Run a single watch tick. Returns the number of jobs enqueued (0 or 2)."""
    with session_scope(db_path) as session:
        result = register_footage(session, footage_dir)

    if result.new == 0:
        logger.debug("watch: no new footage under %s", footage_dir)
        return 0

    logger.info(
        "watch: found %d new file(s) under %s; settling for %.0fs",
        result.new,
        footage_dir,
        SETTLE_S,
    )
    time.sleep(SETTLE_S)

    # Settle pass: catch files that finished uploading (or newly appeared) during
    # the wait, so the index/scan jobs below see a stable footage tree.
    with session_scope(db_path) as session:
        register_footage(session, footage_dir)

    with session_scope(db_path) as session:
        queue.enqueue(session, "index", {"footage_dir": str(footage_dir)})
        queue.enqueue(session, "scan", {"footage_dir": str(footage_dir)})
    logger.info("watch: enqueued index + scan jobs")

    if not enqueue_only:
        processed = run_pending_jobs(db_path)
        logger.info("watch: drained %d job(s)", processed)

    return 2


def watch_loop(
    cfg: Config,
    db_path: str,
    *,
    interval_s: float = 60.0,
    once: bool = False,
    enqueue_only: bool | None = None,
    stop_event: threading.Event | None = None,
) -> None:
    """Poll ``cfg.general.footage_dir`` for new footage and enqueue processing jobs.

    ``once=True`` runs a single tick and returns (used by tests and one-shot manual
    runs). Otherwise loops, sleeping ``interval_s`` between ticks, until
    ``stop_event`` is set or a ``KeyboardInterrupt`` is raised (caught here so
    ``Ctrl+C`` stops cleanly rather than printing a traceback).
    """
    if not cfg.general.footage_dir:
        raise ValueError("[general].footage_dir is not configured")
    footage_dir = Path(cfg.general.footage_dir)

    resolved_enqueue_only = (
        _default_enqueue_only() if enqueue_only is None else enqueue_only
    )
    event = stop_event if stop_event is not None else threading.Event()

    logger.info(
        "watch daemon starting: footage_dir=%s interval=%ss enqueue_only=%s",
        footage_dir,
        interval_s,
        resolved_enqueue_only,
    )
    try:
        while True:
            _tick(
                cfg,
                db_path,
                footage_dir=footage_dir,
                enqueue_only=resolved_enqueue_only,
            )
            if once:
                break
            if event.wait(interval_s):
                break
    except KeyboardInterrupt:
        logger.info("watch daemon interrupted; stopping")
    logger.info("watch daemon stopped")
