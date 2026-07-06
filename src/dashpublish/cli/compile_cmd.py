"""``dashpublish compile`` — plan (LLM EDL) and render a compilation.

Reuses the exact same job tasks the API uses (``compile`` jobs with
``action=plan``/``action=render``, see :mod:`dashpublish.jobs.tasks`) via enqueue +
:func:`dashpublish.jobs.tasks.run_pending_jobs`, instead of re-implementing planning
or rendering here.

Note: a few early-raise paths in ``jobs.tasks`` (e.g. the LLM provider failing to
construct, or rendering being asked to run with no EDL yet) raise before the task's
own try/except updates the compilation row, so the job ends up ``error`` while the
compilation is left stuck in ``planning``/``rendering``. This command treats *either*
signal (job status or compilation status) as failure so it never reports success on a
job that actually errored.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from dashpublish.cli._common import ensure_db, get_cfg
from dashpublish.db import repo
from dashpublish.db.engine import session_scope
from dashpublish.jobs import queue
from dashpublish.jobs.tasks import run_pending_jobs

VALID_PROFILES = ("short", "long")
VALID_FROM = ("starred", "top")


def compile_(
    profile: str = typer.Option("short", "--profile", help="short|long"),
    from_: str = typer.Option(
        "top", "--from", help="Candidate selection when --clips is not given: starred|top"
    ),
    clips: Optional[str] = typer.Option(
        None, "--clips", help="Comma-separated clip ids to use exactly (skips selection)."
    ),
    music: Optional[Path] = typer.Option(
        None, "--music", help="Optional music file to duck under clip audio."
    ),
    title: Optional[str] = typer.Option(None, "--title", help="Initial compilation title."),
    plan_only: bool = typer.Option(
        False, "--plan-only", help="Plan the EDL and print it as JSON; do not render."
    ),
) -> None:
    """Plan and render a compilation from starred/top clips (or an explicit --clips list)."""
    if profile not in VALID_PROFILES:
        typer.echo(f"--profile must be one of {VALID_PROFILES}", err=True)
        raise typer.Exit(1)
    if from_ not in VALID_FROM:
        typer.echo(f"--from must be one of {VALID_FROM}", err=True)
        raise typer.Exit(1)

    cfg = get_cfg()
    db_path, _ = ensure_db(cfg)

    clip_ids = [int(x) for x in clips.split(",") if x.strip()] if clips else None
    stash = {"clip_ids": clip_ids, "from_selection": from_}

    with session_scope(db_path) as session:
        comp = repo.create_compilation(
            session, profile=profile, title=title, music_path=str(music) if music else None
        )
        repo.update_compilation(session, comp.id, edl_json={"_candidates": stash})
        comp_id = comp.id

    typer.echo(f"Created compilation {comp_id}; planning...")
    with session_scope(db_path) as session:
        repo.update_compilation(session, comp_id, status="planning", error=None)
        plan_job_id = queue.enqueue(
            session, "compile", {"action": "plan", "compilation_id": comp_id}
        ).id
    run_pending_jobs(db_path)

    with session_scope(db_path) as session:
        comp = repo.get_compilation(session, comp_id)
        job = queue.get_job(session, plan_job_id)
        status, edl_json, error = comp.status, comp.edl_json, comp.error
        job_error = job.error if job is not None else None
        job_failed = job is not None and job.status == "error"

    if status == "failed" or job_failed:
        typer.echo(f"Planning failed: {error or job_error}", err=True)
        raise typer.Exit(1)

    if plan_only:
        typer.echo(json.dumps(edl_json, indent=2, default=str))
        return

    typer.echo(f"Compilation {comp_id} planned; rendering...")
    with session_scope(db_path) as session:
        repo.update_compilation(session, comp_id, status="rendering", error=None)
        render_job_id = queue.enqueue(
            session, "compile", {"action": "render", "compilation_id": comp_id}
        ).id
    run_pending_jobs(db_path)

    with session_scope(db_path) as session:
        comp = repo.get_compilation(session, comp_id)
        job = queue.get_job(session, render_job_id)
        status, output_path, error, edl_json = (
            comp.status,
            comp.output_path,
            comp.error,
            comp.edl_json,
        )
        job_error = job.error if job is not None else None
        job_failed = job is not None and job.status == "error"

    if status == "failed" or job_failed:
        typer.echo(f"Render failed: {error or job_error}", err=True)
        raise typer.Exit(1)

    duration = sum(
        max(0.0, seg.get("trim_end_s", 0) - seg.get("trim_start_s", 0))
        for seg in (edl_json or {}).get("segments", [])
    )
    typer.echo(f"Compilation {comp_id} rendered: {output_path} (~{duration:.1f}s)")
