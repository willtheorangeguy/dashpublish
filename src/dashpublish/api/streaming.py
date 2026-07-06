"""HTTP Range-aware file streaming (RFC 7233) for video playback.

:func:`range_file_response` serves a file either whole (200) or as a byte range
(206), streaming in 1 MiB chunks. Suffix ranges (``bytes=-500``) and open-ended
ranges (``bytes=100-``) are supported; malformed / unsatisfiable ranges yield 416.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterator

from starlette.responses import FileResponse, Response, StreamingResponse

CHUNK_SIZE = 1024 * 1024  # 1 MiB

_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


def _parse_range(range_header: str, file_size: int) -> tuple[int, int] | None:
    """Parse a single-range ``Range`` header into an inclusive ``(start, end)``.

    Returns ``None`` when the header is malformed or the range is unsatisfiable
    (the caller should answer 416 in that case).
    """
    match = _RANGE_RE.match(range_header.strip())
    if match is None:
        return None
    start_s, end_s = match.group(1), match.group(2)

    if start_s == "" and end_s == "":
        return None
    if start_s == "":
        # Suffix range: last N bytes.
        length = int(end_s)
        if length <= 0:
            return None
        start = max(0, file_size - length)
        end = file_size - 1
    else:
        start = int(start_s)
        end = int(end_s) if end_s != "" else file_size - 1

    if start > end or start >= file_size:
        return None
    end = min(end, file_size - 1)
    return start, end


def _iter_file(path: Path, start: int, length: int) -> Iterator[bytes]:
    with path.open("rb") as fh:
        fh.seek(start)
        remaining = length
        while remaining > 0:
            chunk = fh.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def range_file_response(
    path: str | os.PathLike[str],
    range_header: str | None,
    media_type: str = "video/mp4",
) -> Response:
    """Return a full (200) or partial (206) response for ``path``.

    The file is assumed to exist; callers should 404 beforehand when it does not.
    """
    file_path = Path(path)
    file_size = file_path.stat().st_size

    if not range_header:
        return FileResponse(
            file_path,
            media_type=media_type,
            headers={"Accept-Ranges": "bytes"},
        )

    parsed = _parse_range(range_header, file_size)
    if parsed is None:
        return Response(
            status_code=416,
            headers={"Content-Range": f"bytes */{file_size}", "Accept-Ranges": "bytes"},
        )

    start, end = parsed
    length = end - start + 1
    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
    }
    return StreamingResponse(
        _iter_file(file_path, start, length),
        status_code=206,
        media_type=media_type,
        headers=headers,
    )
