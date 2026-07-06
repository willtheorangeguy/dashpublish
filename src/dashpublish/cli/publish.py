"""``dashpublish publish`` — upload rendered compilations and flip them public."""

from __future__ import annotations

from typing import Any, Optional

import typer

from dashpublish.cli._common import ensure_db, get_cfg
from dashpublish.compile.edl import EDL, ClipInfo
from dashpublish.compile.profiles import get_profile
from dashpublish.db import repo
from dashpublish.db.engine import session_scope
from dashpublish.llm.factory import get_provider
from dashpublish.metadata.generate import generate_metadata
from dashpublish.youtube import (
    CompilationNotReadyError,
    NotAuthenticatedError,
    UploadError,
    YouTubePublisher,
)

app = typer.Typer(help="Upload and publish compilations to YouTube.")

_PUBLISH_ERRORS = (ValueError, CompilationNotReadyError, NotAuthenticatedError, UploadError)


def _clip_info(clip: Any) -> ClipInfo:
    return ClipInfo(
        id=clip.id,
        duration_s=max(0.0, clip.end_s - clip.start_s),
        category=clip.category.name if clip.category is not None else None,
        score=clip.score,
        clip_path=clip.clip_path,
    )


def _watch_url(video_id: str | None) -> str:
    return f"https://youtu.be/{video_id}"


@app.command("upload")
def upload(
    compilation_id: int,
    title: Optional[str] = typer.Option(None, "--title"),
    description: Optional[str] = typer.Option(None, "--description"),
    tags: Optional[str] = typer.Option(None, "--tags", help="Comma-separated tags."),
) -> None:
    """Upload a rendered compilation to YouTube (generating missing metadata first)."""
    cfg = get_cfg()
    db_path, _ = ensure_db(cfg)

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags is not None else None

    if title is None or description is None or tag_list is None:
        with session_scope(db_path) as session:
            comp = repo.get_compilation(session, compilation_id)
            if comp is None:
                typer.echo(f"Compilation {compilation_id} not found", err=True)
                raise typer.Exit(1)
            if not comp.edl_json or "segments" not in comp.edl_json:
                typer.echo("Compilation has no EDL; run 'dashpublish compile' first.", err=True)
                raise typer.Exit(1)
            edl = EDL.model_validate(comp.edl_json)
            profile = get_profile(comp.profile, cfg)
            clip_map: dict[int, ClipInfo] = {}
            for seg in edl.segments:
                clip = repo.get_clip(session, seg.clip_id)
                if clip is not None:
                    clip_map[clip.id] = _clip_info(clip)

        provider = get_provider(cfg)
        meta = generate_metadata(provider, edl=edl, clips=clip_map, profile=profile)
        title = title or meta.title
        description = meta.description if description is None else description
        tag_list = meta.tags if tag_list is None else tag_list

        typer.echo("Generated metadata:")
        typer.echo(f"  title:       {title}")
        typer.echo(f"  description: {description}")
        typer.echo(f"  tags:        {', '.join(tag_list)}")

    publisher = YouTubePublisher(cfg, db_path)
    try:
        record = publisher.upload_compilation(
            compilation_id, title=title, description=description or "", tags=tag_list or []
        )
    except _PUBLISH_ERRORS as exc:
        typer.echo(f"Upload failed: {exc}", err=True)
        raise typer.Exit(1) from exc

    typer.echo(
        f"Uploaded: video_id={record.youtube_video_id} url={_watch_url(record.youtube_video_id)}"
    )


@app.command("go")
def go(record_id: int) -> None:
    """Flip an uploaded video's privacy to public."""
    cfg = get_cfg()
    db_path, _ = ensure_db(cfg)
    publisher = YouTubePublisher(cfg, db_path)
    try:
        record = publisher.publish(record_id)
    except _PUBLISH_ERRORS as exc:
        typer.echo(f"Publish failed: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"Published: {_watch_url(record.youtube_video_id)}")
