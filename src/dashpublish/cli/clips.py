"""``dashpublish clips`` — browse and curate detected clips."""

from __future__ import annotations

import json
from typing import Any, Optional

import typer

from dashpublish.cli._common import ensure_db, get_cfg
from dashpublish.db import repo
from dashpublish.db.engine import session_scope
from dashpublish.db.schemas import ClipPatch

app = typer.Typer(help="Browse and curate detected clips.")


def _row(clip: Any) -> dict:
    return {
        "id": clip.id,
        "category": clip.category.name if clip.category is not None else None,
        "score": round(clip.score, 3),
        "start_s": clip.start_s,
        "end_s": clip.end_s,
        "starred": clip.starred,
        "path": clip.clip_path,
    }


@app.command("list")
def list_clips(
    category: Optional[str] = typer.Option(
        None, "--category", help="Filter by category name."
    ),
    starred: bool = typer.Option(
        False, "--starred", help="Only show starred clips."
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Print JSON instead of a table."
    ),
) -> None:
    """List detected clips (id, category, score, time range, starred, path)."""
    cfg = get_cfg()
    db_path, _ = ensure_db(cfg)
    with session_scope(db_path) as session:
        clips = repo.list_clips(session, category=category, starred=starred or None)
        rows = [_row(c) for c in clips]

    if json_out:
        typer.echo(json.dumps(rows, indent=2))
        return

    if not rows:
        typer.echo("No clips found.")
        return

    typer.echo(f"{'ID':>5}  {'CATEGORY':<14}  {'SCORE':>6}  {'RANGE':>15}  *  PATH")
    for row in rows:
        rng = f"{row['start_s']:.1f}-{row['end_s']:.1f}"
        star = "*" if row["starred"] else " "
        typer.echo(
            f"{row['id']:>5}  {(row['category'] or '-'):<14}  {row['score']:>6.3f}  "
            f"{rng:>15}  {star}  {row['path'] or '-'}"
        )


@app.command("star")
def star(
    clip_id: int,
    unstar: bool = typer.Option(False, "--unstar", help="Unstar instead of star."),
) -> None:
    """Star (or ``--unstar``) a clip by id."""
    cfg = get_cfg()
    db_path, _ = ensure_db(cfg)
    with session_scope(db_path) as session:
        clip = repo.patch_clip(session, clip_id, ClipPatch(starred=not unstar))
        found = clip is not None

    if not found:
        typer.echo(f"Clip {clip_id} not found", err=True)
        raise typer.Exit(1)
    typer.echo(f"Clip {clip_id} {'unstarred' if unstar else 'starred'}.")
