"""Real-ffmpeg smoke test: render a short-form compilation from generated clips.

Auto-skips when no ffmpeg binary can be resolved (PATH or FFMPEG_PATH env var).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from dashpublish.compile.edl import EDL, ClipInfo, EDLSegment, validate_and_fix
from dashpublish.compile.profiles import get_profile
from dashpublish.compile.render import probe_dimensions, render, resolve_ffmpeg

pytestmark = pytest.mark.ffmpeg

FFMPEG = resolve_ffmpeg()


def generate_test_clip(path: Path, seconds: int = 5) -> None:
    """Generate a 1280x720 test clip with a sine audio track."""
    subprocess.run(
        [
            FFMPEG,
            "-hide_banner",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size=1280x720:rate=30:duration={seconds}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not found on PATH or via FFMPEG_PATH")
def test_short_profile_render_smoke(tmp_path: Path):
    clip1 = tmp_path / "clip1.mp4"
    clip2 = tmp_path / "clip2.mp4"
    generate_test_clip(clip1)
    generate_test_clip(clip2)

    clips = {
        1: ClipInfo(id=1, duration_s=5.0, category="crash", score=0.9, clip_path=str(clip1)),
        2: ClipInfo(id=2, duration_s=5.0, category="funny", score=0.7, clip_path=str(clip2)),
    }
    profile = get_profile("short")
    edl = EDL(
        profile="short",
        target_duration_s=profile.target_duration_s,
        segments=[
            EDLSegment(clip_id=1, trim_start_s=0.5, trim_end_s=4.5, order=0),
            EDLSegment(clip_id=2, trim_start_s=0.0, trim_end_s=4.0, order=1),
        ],
    )
    edl = validate_and_fix(edl, clips, profile)

    output = tmp_path / "out" / "compilation.mp4"
    progress: list[float] = []
    result = render(
        edl, clips, profile, str(output), ffmpeg_path=FFMPEG, progress_cb=progress.append
    )

    assert Path(result.output_path).exists()
    assert Path(result.output_path).stat().st_size > 0
    assert progress == [0.0, 1.0]

    dims = probe_dimensions(result.output_path, FFMPEG)
    assert dims is not None, "ffprobe should sit next to ffmpeg"
    assert dims == (1080, 1920)

    assert result.duration_s is not None
    assert result.duration_s <= 60.0
    assert result.duration_s == pytest.approx(8.0, abs=0.75)  # 4s + 4s
