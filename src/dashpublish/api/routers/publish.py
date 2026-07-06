"""YouTube upload + publish (synchronous in API v1) and record listing.

Uploads run synchronously in the request. In fake mode this is instant; in real
mode a resumable YouTube upload can be slow, but for a single-user local tool a
synchronous upload is acceptable (the ``upload`` job task exists for CLI/G use).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from dashpublish.api.deps import get_db_path, get_effective_config
from dashpublish.api.models import PublishApiOut
from dashpublish.db import repo
from dashpublish.db.engine import session_scope
from dashpublish.youtube import (
    CompilationNotReadyError,
    NotAuthenticatedError,
    UploadError,
    YouTubePublisher,
)
from pydantic import BaseModel

router = APIRouter(prefix="/publish", tags=["publish"])


class UploadBody(BaseModel):
    title: str
    description: str = ""
    tags: list[str] = []


@router.get("", response_model=list[PublishApiOut])
def list_publish_records(db_path: str = Depends(get_db_path)) -> list[PublishApiOut]:
    with session_scope(db_path) as session:
        return [PublishApiOut.from_record(r) for r in repo.list_publish_records(session)]


@router.post("/{compilation_id}/upload", response_model=PublishApiOut)
def upload(
    compilation_id: int,
    body: UploadBody,
    db_path: str = Depends(get_db_path),
    cfg=Depends(get_effective_config),
) -> PublishApiOut:
    publisher = YouTubePublisher(cfg, db_path)
    try:
        record = publisher.upload_compilation(
            compilation_id,
            title=body.title,
            description=body.description,
            tags=body.tags,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CompilationNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except NotAuthenticatedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UploadError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return PublishApiOut.from_record(record)


@router.post("/{publish_record_id}/publish", response_model=PublishApiOut)
def publish(
    publish_record_id: int,
    db_path: str = Depends(get_db_path),
    cfg=Depends(get_effective_config),
) -> PublishApiOut:
    publisher = YouTubePublisher(cfg, db_path)
    try:
        record = publisher.publish(publish_record_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CompilationNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except NotAuthenticatedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UploadError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return PublishApiOut.from_record(record)
