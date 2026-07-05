"""Resumable YouTube video upload.

Uploads are chunked (8 MiB) and resumable; each chunk is retried up to 3 times on
transient (HTTP 5xx) errors with exponential backoff. Any other failure raises
:class:`UploadError`.
"""

from __future__ import annotations

import time
from typing import Callable

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

MAX_TITLE_LEN = 100
MAX_DESCRIPTION_LEN = 5000
CHUNK_SIZE = 8 * 1024 * 1024
MAX_CHUNK_RETRIES = 3


class UploadError(RuntimeError):
    """The upload failed and could not be retried."""


def _is_retryable(exc: HttpError) -> bool:
    status = getattr(exc.resp, "status", None)
    if status is None:
        return False
    try:
        code = int(status)
    except (TypeError, ValueError):
        return False
    return 500 <= code < 600


def _next_chunk_with_retry(request, *, max_retries: int = MAX_CHUNK_RETRIES):
    """Call ``request.next_chunk()``, retrying up to ``max_retries`` times on 5xx."""
    attempt = 0
    while True:
        try:
            return request.next_chunk()
        except HttpError as exc:
            if not _is_retryable(exc):
                raise UploadError(f"YouTube upload failed: {exc}") from exc
            attempt += 1
            if attempt > max_retries:
                raise UploadError(
                    f"YouTube upload failed after {max_retries} retries: {exc}"
                ) from exc
            time.sleep(min(2**attempt, 30))


def upload_video(
    service,
    *,
    file_path: str,
    title: str,
    description: str,
    tags: list[str],
    privacy: str = "private",
    category_id: str = "2",
    progress_cb: Callable[[float], None] | None = None,
) -> str:
    """Upload ``file_path`` to YouTube and return the new video id.

    ``progress_cb`` (if given) receives the upload fraction (0.0-1.0) after each
    chunk and a final ``1.0`` on completion.
    """
    body = {
        "snippet": {
            "title": title[:MAX_TITLE_LEN],
            "description": description[:MAX_DESCRIPTION_LEN],
            "tags": list(tags),
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(
        file_path, chunksize=CHUNK_SIZE, resumable=True, mimetype="video/mp4"
    )
    request = service.videos().insert(
        part="snippet,status", body=body, media_body=media
    )

    response = None
    while response is None:
        status, response = _next_chunk_with_retry(request)
        if status is not None and progress_cb is not None:
            progress_cb(status.progress())

    video_id = (response or {}).get("id")
    if not video_id:
        raise UploadError(f"YouTube upload returned no video id: {response!r}")
    if progress_cb is not None:
        progress_cb(1.0)
    return video_id
