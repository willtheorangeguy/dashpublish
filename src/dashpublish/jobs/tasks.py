"""Background job task implementations and the dispatch entry point.

``run_job`` is the single entry point the worker (and CLI/tests) call. It reads a
job row, dispatches by ``type`` (with ``compile`` jobs sub-dispatched on the
payload ``action`` — ``plan`` / ``render``), and always records completion or the
error string via :mod:`dashpublish.jobs.queue`; a task raising never crashes the
worker.

Job types are constrained to the DB ``JobType`` literal (index/scan/compile/
upload/publish), so compilation *planning* and *rendering* both ride on the
``compile`` type and are told apart by ``payload["action"]``.
"""

from __future__ import annotations

from pathlib import Path

from dashpublish.api.deps import effective_config
from dashpublish.compile.edl import EDL, ClipInfo
from dashpublish.compile.planner import gather_candidates, plan_edl
from dashpublish.compile.profiles import get_profile
from dashpublish.compile.render import RenderError, render
from dashpublish.db import repo
from dashpublish.db.engine import session_scope
from dashpublish.ingest import register_footage
from dashpublish.jobs import queue
from dashpublish.llm.factory import get_provider
from dashpublish.logging import get_logger
from dashpublish.paths import resolve_paths
from dashpublish.sentry import FakeSentryClient, SentrySearchClient, ensure_indexed, run_scan

logger = get_logger(__name__)


# --- helpers --------------------------------------------------------------


def _make_sentry_client(cfg):
    if cfg.fake_mode:
        return FakeSentryClient()
    return SentrySearchClient(backend=cfg.embeddings.backend)


def _clipinfo(clip) -> ClipInfo:
    return ClipInfo(
        id=clip.id,
        duration_s=max(0.0, clip.end_s - clip.start_s),
        category=clip.category.name if clip.category is not None else None,
        score=clip.score,
        clip_path=clip.clip_path,
    )


def _progress(db_path, job_id: int, fraction: float, message: str | None = None) -> None:
    """Write job progress in its own short transaction (safe outside heavy work)."""
    with session_scope(db_path) as session:
        queue.update_progress(session, job_id, fraction, message)


def _resync_compilation_clips(session, compilation_id: int, edl: EDL) -> None:
    """Replace ``compilation_clips`` rows to mirror the EDL segments in order."""
    for existing in repo.list_compilation_clips(session, compilation_id):
        session.delete(existing)
    session.flush()
    items = [
        {
            "clip_id": seg.clip_id,
            "order_index": seg.order,
            "trim_start": seg.trim_start_s,
            "trim_end": seg.trim_end_s,
        }
        for seg in sorted(edl.segments, key=lambda s: s.order)
    ]
    repo.add_compilation_clips(session, compilation_id, items)


# --- individual tasks -----------------------------------------------------


def _task_index(db_path, job_id: int, payload: dict) -> None:
    cfg = effective_config(db_path)
    client = _make_sentry_client(cfg)
    footage_dir = payload.get("footage_dir") or cfg.general.footage_dir
    with session_scope(db_path) as session:
        def cb(message: str, fraction: float) -> None:
            queue.update_progress(session, job_id, fraction, message)

        if footage_dir:
            register_footage(session, Path(footage_dir))
        ensure_indexed(session, client, progress_cb=cb)


def _task_scan(db_path, job_id: int, payload: dict) -> None:
    cfg = effective_config(db_path)
    paths = resolve_paths(cfg)
    client = _make_sentry_client(cfg)
    footage_dir = payload.get("footage_dir") or cfg.general.footage_dir
    with session_scope(db_path) as session:
        def cb(message: str, fraction: float) -> None:
            queue.update_progress(session, job_id, fraction, message)

        if footage_dir:
            register_footage(session, Path(footage_dir))
        ensure_indexed(session, client, progress_cb=cb)
        run_scan(session, client, paths.clips_dir, scan_cfg=cfg.scan, progress_cb=cb)


def _task_plan(db_path, job_id: int, payload: dict) -> None:
    compilation_id = payload["compilation_id"]
    cfg = effective_config(db_path)
    provider = get_provider(cfg)
    try:
        with session_scope(db_path) as session:
            comp = repo.get_compilation(session, compilation_id)
            if comp is None:
                raise ValueError(f"Compilation {compilation_id} not found")
            stash = (comp.edl_json or {}).get("_candidates", {}) or {}
            clip_ids = stash.get("clip_ids")
            from_selection = stash.get("from_selection") or "top"
            music_path = comp.music_path
            profile = get_profile(comp.profile, cfg)

            queue.update_progress(session, job_id, 0.2, "gathering candidates")
            candidates = gather_candidates(
                session, profile, clip_ids=clip_ids, from_selection=from_selection
            )
            queue.update_progress(session, job_id, 0.5, "planning with LLM")
            edl = plan_edl(
                provider,
                candidates,
                profile,
                music_path=music_path,
                transition=cfg.compile.transition,
            )
            repo.update_compilation(
                session,
                compilation_id,
                edl_json=edl.model_dump(),
                status="draft",
                error=None,
            )
            _resync_compilation_clips(session, compilation_id, edl)
    except Exception as exc:  # noqa: BLE001 - record on the row + re-raise for the job
        with session_scope(db_path) as session:
            repo.update_compilation(
                session, compilation_id, status="failed", error=str(exc)
            )
        raise


def _task_render(db_path, job_id: int, payload: dict) -> None:
    compilation_id = payload["compilation_id"]
    cfg = effective_config(db_path)
    paths = resolve_paths(cfg)

    with session_scope(db_path) as session:
        comp = repo.get_compilation(session, compilation_id)
        if comp is None:
            raise ValueError(f"Compilation {compilation_id} not found")
        if not comp.edl_json or "segments" not in comp.edl_json:
            raise ValueError(f"Compilation {compilation_id} has no EDL to render")
        edl = EDL.model_validate(comp.edl_json)
        profile = get_profile(comp.profile, cfg)
        clips: dict[int, ClipInfo] = {}
        for seg in edl.segments:
            clip = repo.get_clip(session, seg.clip_id)
            if clip is not None:
                clips[clip.id] = _clipinfo(clip)
        repo.update_compilation(session, compilation_id, status="rendering", error=None)

    output_path = paths.compilations_dir / f"comp_{compilation_id}.mp4"
    try:
        result = render(
            edl,
            clips,
            profile,
            str(output_path),
            progress_cb=lambda f: _progress(db_path, job_id, f),
        )
    except RenderError as exc:
        with session_scope(db_path) as session:
            repo.update_compilation(
                session, compilation_id, status="failed", error=str(exc)
            )
        raise

    with session_scope(db_path) as session:
        repo.update_compilation(
            session,
            compilation_id,
            output_path=result.output_path,
            status="rendered",
            error=None,
        )


def _task_upload(db_path, job_id: int, payload: dict) -> None:
    """Optional job path for uploads (the API v1 uploads synchronously instead)."""
    from dashpublish.youtube import YouTubePublisher

    cfg = effective_config(db_path)
    publisher = YouTubePublisher(cfg, db_path)
    publisher.upload_compilation(
        payload["compilation_id"],
        title=payload.get("title") or "Dashcam Compilation",
        description=payload.get("description", ""),
        tags=payload.get("tags"),
        progress_cb=lambda f: _progress(db_path, job_id, f),
    )


def _task_publish(db_path, job_id: int, payload: dict) -> None:
    from dashpublish.youtube import YouTubePublisher

    cfg = effective_config(db_path)
    publisher = YouTubePublisher(cfg, db_path)
    publisher.publish(payload["publish_record_id"])


# --- dispatch -------------------------------------------------------------


def run_job(job_id: int, db_path) -> None:
    """Run a single job to completion, recording success or failure on the row."""
    with session_scope(db_path) as session:
        job = queue.get_job(session, job_id)
        if job is None:
            logger.warning("run_job: job %s not found", job_id)
            return
        jtype = job.type
        payload = dict(job.payload_json or {})

    try:
        if jtype == "index":
            _task_index(db_path, job_id, payload)
        elif jtype == "scan":
            _task_scan(db_path, job_id, payload)
        elif jtype == "compile":
            action = payload.get("action")
            if action == "plan":
                _task_plan(db_path, job_id, payload)
            elif action == "render":
                _task_render(db_path, job_id, payload)
            else:
                raise ValueError(f"compile job has unknown action {action!r}")
        elif jtype == "upload":
            _task_upload(db_path, job_id, payload)
        elif jtype == "publish":
            _task_publish(db_path, job_id, payload)
        else:
            raise ValueError(f"unknown job type {jtype!r}")
    except Exception as exc:  # noqa: BLE001 - a task must never crash the worker
        logger.exception("job %s (%s) failed", job_id, jtype)
        with session_scope(db_path) as session:
            queue.finish(session, job_id, error=str(exc))
            # Safety net: a compile task can fail before its own handler runs
            # (e.g. provider setup), leaving the compilation stuck in a
            # transient status that the UI polls indefinitely.
            comp_id = payload.get("compilation_id") if jtype == "compile" else None
            if comp_id is not None:
                comp = repo.get_compilation(session, comp_id)
                if comp is not None and comp.status in ("planning", "rendering"):
                    repo.update_compilation(session, comp_id, status="failed", error=str(exc))
        return

    with session_scope(db_path) as session:
        queue.finish(session, job_id)


def run_pending_jobs(db_path) -> int:
    """Synchronously claim and run every queued job (for tests / CLI one-shots).

    Returns the number of jobs processed.
    """
    processed = 0
    while True:
        with session_scope(db_path) as session:
            job = queue.claim_next(session)
            job_id = job.id if job is not None else None
        if job_id is None:
            break
        run_job(job_id, db_path)
        processed += 1
    return processed
