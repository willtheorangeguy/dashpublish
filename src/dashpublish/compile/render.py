"""ffmpeg rendering: argv construction (pure) and subprocess execution."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from dashpublish.compile.audio import build_music_filter
from dashpublish.compile.edl import EDL, ClipInfo
from dashpublish.compile.profiles import Profile

STDERR_TAIL_CHARS = 2000


class RenderError(RuntimeError):
    """Raised when ffmpeg cannot be found or exits non-zero."""


@dataclass(frozen=True)
class RenderResult:
    output_path: str
    duration_s: float | None


def resolve_ffmpeg(explicit: str | None = None) -> str | None:
    """Locate the ffmpeg binary: explicit path -> PATH -> FFMPEG_PATH env var."""
    if explicit:
        return explicit
    found = shutil.which("ffmpeg")
    if found:
        return found
    env_path = os.environ.get("FFMPEG_PATH")
    if env_path and Path(env_path).exists():
        return env_path
    return None


def resolve_ffprobe(ffmpeg_path: str) -> str | None:
    """Locate ffprobe: sibling of the ffmpeg binary, else PATH."""
    ffmpeg = Path(ffmpeg_path)
    name = "ffprobe" + ffmpeg.suffix if ffmpeg.suffix else "ffprobe"
    sibling = ffmpeg.parent / name
    if sibling.exists():
        return str(sibling)
    return shutil.which("ffprobe")


def build_render_plan(
    edl: EDL,
    clips: dict[int, ClipInfo],
    profile: Profile,
    output_path: str,
    *,
    ffmpeg: str = "ffmpeg",
) -> list[str]:
    """Build the full ffmpeg argv for an EDL. Pure function — no I/O.

    Layout: one ``-ss/-to/-i`` triple per segment (input-side trims for fast
    seek), optional music input last, one ``-filter_complex`` doing per-segment
    video normalization (``profile.vf_chain``) + audio resample, an A/V concat,
    and (when music is enabled) the ducking chain from
    :mod:`dashpublish.compile.audio`.

    Notes:
    - Segment sources are assumed to carry an audio stream (dashcam clips saved
      by the scan pipeline always do).
    - ``transition="crossfade"`` is intentionally rendered as plain cuts in v1.
    """
    segments = sorted(edl.segments, key=lambda s: s.order)
    if not segments:
        raise RenderError("EDL has no segments to render")

    argv: list[str] = [ffmpeg, "-hide_banner", "-y"]
    for seg in segments:
        info = clips.get(seg.clip_id)
        if info is None or not info.clip_path:
            raise RenderError(f"segment references clip {seg.clip_id} with no clip_path")
        argv += [
            "-ss",
            f"{seg.trim_start_s:.3f}",
            "-to",
            f"{seg.trim_end_s:.3f}",
            "-i",
            str(info.clip_path),
        ]

    music_enabled = bool(edl.music.enabled and edl.music.path)
    n = len(segments)
    if music_enabled:
        argv += ["-i", str(edl.music.path)]

    parts: list[str] = []
    for i in range(n):
        parts.append(f"[{i}:v]{profile.vf_chain}[v{i}]")
        parts.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}]")
    concat_inputs = "".join(f"[v{i}][a{i}]" for i in range(n))
    parts.append(f"{concat_inputs}concat=n={n}:v=1:a=1[vc][ac]")

    audio_label = "ac"
    if music_enabled:
        total_s = sum(s.trim_end_s - s.trim_start_s for s in segments)
        music_parts, audio_label = build_music_filter(n, "ac", total_s, edl.music.duck_db)
        parts += music_parts

    argv += ["-filter_complex", ";".join(parts)]
    argv += ["-map", "[vc]", "-map", f"[{audio_label}]"]
    argv += [
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        "-r",
        "30",
        str(output_path),
    ]
    return argv


def probe_duration(path: str, ffmpeg_path: str) -> float | None:
    """Return the container duration in seconds via ffprobe, or None."""
    ffprobe = resolve_ffprobe(ffmpeg_path)
    if ffprobe is None:
        return None
    proc = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return None


def probe_dimensions(path: str, ffmpeg_path: str) -> tuple[int, int] | None:
    """Return ``(width, height)`` of the first video stream, or None."""
    ffprobe = resolve_ffprobe(ffmpeg_path)
    if ffprobe is None:
        return None
    proc = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=s=x:p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    try:
        width, height = proc.stdout.strip().split("x")
        return int(width), int(height)
    except ValueError:
        return None


def render(
    edl: EDL,
    clips: dict[int, ClipInfo],
    profile: Profile,
    output_path: str,
    *,
    ffmpeg_path: str | None = None,
    progress_cb: Callable[[float], None] | None = None,
) -> RenderResult:
    """Render an EDL to ``output_path`` with ffmpeg.

    ``progress_cb`` (if given) receives 0.0 before the render starts and 1.0
    after it completes; fine-grained ffmpeg progress parsing is out of scope.
    """
    ffmpeg = resolve_ffmpeg(ffmpeg_path)
    if ffmpeg is None:
        raise RenderError(
            "ffmpeg not found. Install ffmpeg and put it on PATH, or set the "
            "FFMPEG_PATH environment variable to the ffmpeg binary."
        )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    argv = build_render_plan(edl, clips, profile, str(output_path), ffmpeg=ffmpeg)

    if progress_cb is not None:
        progress_cb(0.0)
    proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or "")[-STDERR_TAIL_CHARS:]
        raise RenderError(f"ffmpeg failed with exit code {proc.returncode}:\n{tail}")

    duration = probe_duration(str(output_path), ffmpeg)
    if progress_cb is not None:
        progress_cb(1.0)
    return RenderResult(output_path=str(output_path), duration_s=duration)
