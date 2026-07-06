"""Compilation CRUD + plan / render / stream / metadata.

Candidate stash decision
------------------------
``POST /compilations`` creates a draft row and stashes the chosen ``clip_ids`` /
``from_selection`` inside ``edl_json`` under a private ``_candidates`` key (there is
no dedicated column). The plan job reads that stash, produces the real EDL, and
overwrites ``edl_json`` with ``edl.model_dump()``. The ``edl`` field in API
responses is exposed only once a real EDL (with ``segments``) exists, so the SPA's
"a plan exists" check stays correct while a draft is still just a stash.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from starlette.responses import Response

from dashpublish.api.deps import get_db_path, get_effective_config
from dashpublish.api.models import (
    CompilationApiOut,
    CompilationCreateIn,
    CompilationPatchIn,
    JobApiOut,
    MetadataApiOut,
)
from dashpublish.api.streaming import range_file_response
from dashpublish.compile.edl import EDL, ClipInfo, EDLValidationError, validate_and_fix
from dashpublish.compile.profiles import get_profile
from dashpublish.db import repo
from dashpublish.db.engine import session_scope
from dashpublish.jobs import queue
from dashpublish.llm.errors import LLMError
from dashpublish.llm.factory import get_provider
from dashpublish.metadata.generate import generate_metadata

router = APIRouter(prefix="/compilations", tags=["compilations"])


def _clipinfo(clip) -> ClipInfo:
    return ClipInfo(
        id=clip.id,
        duration_s=max(0.0, clip.end_s - clip.start_s),
        category=clip.category.name if clip.category is not None else None,
        score=clip.score,
        clip_path=clip.clip_path,
    )


def _normalize_segment(seg: dict) -> dict:
    """Canonicalize a frontend EDL segment onto ``trim_start_s`` / ``trim_end_s``.

    The EDL editor writes ``trim_start`` / ``trim_end`` and may leave stale
    ``trim_start_s`` / ``trim_end_s`` from the loaded plan. Prefer the non-suffixed
    keys when present, write back the canonical ``_s`` keys, and drop the aliases.
    """
    out = dict(seg)
    if "trim_start" in out:
        out["trim_start_s"] = out.pop("trim_start")
    if "trim_end" in out:
        out["trim_end_s"] = out.pop("trim_end")
    out.setdefault("trim_start_s", 0)
    return out


@router.get("", response_model=list[CompilationApiOut])
def list_compilations(db_path: str = Depends(get_db_path)) -> list[CompilationApiOut]:
    with session_scope(db_path) as session:
        return [
            CompilationApiOut.from_orm_compilation(c)
            for c in repo.list_compilations(session)
        ]


@router.get("/{compilation_id}", response_model=CompilationApiOut)
def get_compilation(
    compilation_id: int, db_path: str = Depends(get_db_path)
) -> CompilationApiOut:
    with session_scope(db_path) as session:
        comp = repo.get_compilation(session, compilation_id)
        if comp is None:
            raise HTTPException(status_code=404, detail=f"Compilation {compilation_id} not found")
        return CompilationApiOut.from_orm_compilation(comp)


@router.post("", response_model=CompilationApiOut, status_code=201)
def create_compilation(
    data: CompilationCreateIn, db_path: str = Depends(get_db_path)
) -> CompilationApiOut:
    stash = {
        "clip_ids": data.clip_ids,
        "from_selection": data.from_selection or "top",
    }
    with session_scope(db_path) as session:
        comp = repo.create_compilation(
            session,
            profile=data.profile,
            music_path=data.music_path,
            status="draft",
        )
        repo.update_compilation(session, comp.id, edl_json={"_candidates": stash})
        comp = repo.get_compilation(session, comp.id)
        return CompilationApiOut.from_orm_compilation(comp)


@router.patch("/{compilation_id}", response_model=CompilationApiOut)
def patch_compilation(
    compilation_id: int, patch: CompilationPatchIn, db_path: str = Depends(get_db_path)
) -> CompilationApiOut:
    with session_scope(db_path) as session:
        comp = repo.get_compilation(session, compilation_id)
        if comp is None:
            raise HTTPException(status_code=404, detail=f"Compilation {compilation_id} not found")

        fields: dict = {}
        if patch.title is not None:
            fields["title"] = patch.title
        if patch.music_path is not None:
            fields["music_path"] = patch.music_path

        if patch.edl is not None:
            profile = get_profile(comp.profile)
            raw_segments = [_normalize_segment(s) for s in patch.edl.get("segments", [])]
            # Re-number order sequentially to reflect any reordering.
            for i, seg in enumerate(raw_segments):
                seg.setdefault("order", i)
            edl_data = dict(patch.edl)
            edl_data["segments"] = raw_segments
            edl_data.setdefault("profile", comp.profile)
            edl_data.setdefault("target_duration_s", profile.target_duration_s)

            clips: dict[int, ClipInfo] = {}
            for seg in raw_segments:
                clip = repo.get_clip(session, seg["clip_id"])
                if clip is not None:
                    clips[clip.id] = _clipinfo(clip)
            try:
                edl = EDL.model_validate(edl_data)
                edl = validate_and_fix(edl, clips, profile)
            except (EDLValidationError, ValueError) as exc:
                raise HTTPException(status_code=422, detail=f"Invalid EDL: {exc}") from exc

            fields["edl_json"] = edl.model_dump()
            # Resync compilation_clips to mirror the saved EDL.
            for existing in repo.list_compilation_clips(session, compilation_id):
                session.delete(existing)
            session.flush()
            repo.add_compilation_clips(
                session,
                compilation_id,
                [
                    {
                        "clip_id": s.clip_id,
                        "order_index": s.order,
                        "trim_start": s.trim_start_s,
                        "trim_end": s.trim_end_s,
                    }
                    for s in sorted(edl.segments, key=lambda x: x.order)
                ],
            )

        if fields:
            repo.update_compilation(session, compilation_id, **fields)
        comp = repo.get_compilation(session, compilation_id)
        return CompilationApiOut.from_orm_compilation(comp)


@router.post("/{compilation_id}/plan", response_model=JobApiOut, status_code=202)
def plan_compilation(
    compilation_id: int, db_path: str = Depends(get_db_path)
) -> JobApiOut:
    with session_scope(db_path) as session:
        comp = repo.get_compilation(session, compilation_id)
        if comp is None:
            raise HTTPException(status_code=404, detail=f"Compilation {compilation_id} not found")
        repo.update_compilation(session, compilation_id, status="planning", error=None)
        job = queue.enqueue(
            session, "compile", {"action": "plan", "compilation_id": compilation_id}
        )
        return JobApiOut.from_orm_job(queue.get_job(session, job.id))


@router.post("/{compilation_id}/render", response_model=JobApiOut, status_code=202)
def render_compilation(
    compilation_id: int, db_path: str = Depends(get_db_path)
) -> JobApiOut:
    with session_scope(db_path) as session:
        comp = repo.get_compilation(session, compilation_id)
        if comp is None:
            raise HTTPException(status_code=404, detail=f"Compilation {compilation_id} not found")
        if not comp.edl_json or "segments" not in comp.edl_json:
            raise HTTPException(status_code=409, detail="Compilation has no EDL to render")
        repo.update_compilation(session, compilation_id, status="rendering", error=None)
        job = queue.enqueue(
            session, "compile", {"action": "render", "compilation_id": compilation_id}
        )
        return JobApiOut.from_orm_job(queue.get_job(session, job.id))


@router.get("/{compilation_id}/stream")
def stream_compilation(
    compilation_id: int,
    range: str | None = Header(default=None),
    db_path: str = Depends(get_db_path),
) -> Response:
    with session_scope(db_path) as session:
        comp = repo.get_compilation(session, compilation_id)
        output_path = comp.output_path if comp is not None else None
    if not output_path or not Path(output_path).exists():
        raise HTTPException(status_code=404, detail="Rendered file not available")
    return range_file_response(output_path, range)


@router.post("/{compilation_id}/metadata", response_model=MetadataApiOut)
def compilation_metadata(
    compilation_id: int,
    request: Request,
    db_path: str = Depends(get_db_path),
    cfg=Depends(get_effective_config),
) -> MetadataApiOut:
    provider = get_provider(cfg)
    with session_scope(db_path) as session:
        comp = repo.get_compilation(session, compilation_id)
        if comp is None:
            raise HTTPException(status_code=404, detail=f"Compilation {compilation_id} not found")
        if not comp.edl_json or "segments" not in comp.edl_json:
            raise HTTPException(status_code=409, detail="Compilation has no EDL for metadata")
        edl = EDL.model_validate(comp.edl_json)
        profile = get_profile(comp.profile, cfg)
        clips: dict[int, ClipInfo] = {}
        for seg in edl.segments:
            clip = repo.get_clip(session, seg.clip_id)
            if clip is not None:
                clips[clip.id] = _clipinfo(clip)

        try:
            meta = generate_metadata(provider, edl=edl, clips=clips, profile=profile)
        except LLMError as exc:
            raise HTTPException(status_code=502, detail=f"Metadata generation failed: {exc}") from exc

        repo.update_compilation(session, compilation_id, title=meta.title)
        return MetadataApiOut(title=meta.title, description=meta.description, tags=meta.tags)
