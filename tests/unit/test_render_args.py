"""build_render_plan argv assertions (pure function, no ffmpeg needed)."""

from __future__ import annotations

import pytest

from dashpublish.compile.edl import EDL, ClipInfo, EDLSegment, MusicSpec
from dashpublish.compile.profiles import Profile
from dashpublish.compile.render import RenderError, build_render_plan

SHORT = Profile(
    name="short", width=1080, height=1920, max_duration_s=60, target_duration_s=55,
    min_segment_s=2.0, max_segment_s=10.0,
    vf_chain="crop=ih*9/16:ih,scale=1080:1920,setsar=1,fps=30",
)
LONG = Profile(
    name="long", width=1920, height=1080, max_duration_s=900, target_duration_s=300,
    min_segment_s=4.0, max_segment_s=30.0,
    vf_chain=(
        "scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30"
    ),
)

CLIPS = {
    1: ClipInfo(id=1, duration_s=12.0, category="crash", score=0.9, clip_path="/clips/a.mp4"),
    2: ClipInfo(id=2, duration_s=8.0, category="funny", score=0.7, clip_path="/clips/b.mp4"),
}


def make_edl(music: MusicSpec | None = None) -> EDL:
    return EDL(
        profile="short",
        target_duration_s=55,
        segments=[
            EDLSegment(clip_id=1, trim_start_s=1.0, trim_end_s=6.0, order=0),
            EDLSegment(clip_id=2, trim_start_s=0.0, trim_end_s=5.0, order=1),
        ],
        music=music or MusicSpec(),
    )


def filter_complex_of(argv: list[str]) -> str:
    return argv[argv.index("-filter_complex") + 1]


def test_basic_argv_layout_short():
    argv = build_render_plan(make_edl(), CLIPS, SHORT, "/out/final.mp4", ffmpeg="ffmpeg")

    assert argv[0] == "ffmpeg"
    assert argv[-1] == "/out/final.mp4"  # output path last
    # Input-side -ss/-to before each -i, in segment order.
    i1 = argv.index("/clips/a.mp4")
    assert argv[i1 - 5 : i1] == ["-ss", "1.000", "-to", "6.000", "-i"]
    i2 = argv.index("/clips/b.mp4")
    assert argv[i2 - 5 : i2] == ["-ss", "0.000", "-to", "5.000", "-i"]
    assert i1 < i2

    fc = filter_complex_of(argv)
    assert fc.count("crop=ih*9/16:ih,scale=1080:1920,setsar=1,fps=30") == 2
    assert "[0:v]" in fc and "[1:v]" in fc
    assert "aresample=48000,aformat=channel_layouts=stereo" in fc
    assert "concat=n=2:v=1:a=1[vc][ac]" in fc

    # Codec / container flags.
    assert argv[argv.index("-c:v") + 1] == "libx264"
    assert argv[argv.index("-crf") + 1] == "20"
    assert argv[argv.index("-c:a") + 1] == "aac"
    assert "+faststart" in argv
    assert argv[argv.index("-movflags") + 1] == "+faststart"


def test_no_music_maps_concat_audio_and_has_no_duck_chain():
    argv = build_render_plan(make_edl(), CLIPS, SHORT, "/out/f.mp4")
    fc = filter_complex_of(argv)
    assert "sidechaincompress" not in fc
    assert "amix" not in fc
    maps = [argv[i + 1] for i, a in enumerate(argv) if a == "-map"]
    assert maps == ["[vc]", "[ac]"]
    assert "/music" not in " ".join(argv)


def test_music_enables_duck_chain_and_extra_input():
    edl = make_edl(music=MusicSpec(enabled=True, path="/music/track.mp3", duck_db=-12))
    argv = build_render_plan(edl, CLIPS, SHORT, "/out/f.mp4")

    assert "/music/track.mp3" in argv
    # Music input comes after all segment inputs -> index 2 in the filtergraph.
    fc = filter_complex_of(argv)
    assert "[2:a]volume=-12dB" in fc
    assert "aloop=loop=-1:size=2e9" in fc
    assert "atrim=0:10.000" in fc  # 5s + 5s total
    assert "sidechaincompress=threshold=0.05:ratio=8:attack=20:release=500:makeup=1" in fc
    assert "amix=inputs=2:duration=first:normalize=0[aout]" in fc
    maps = [argv[i + 1] for i, a in enumerate(argv) if a == "-map"]
    assert maps == ["[vc]", "[aout]"]


def test_long_profile_uses_pad_chain():
    edl = EDL(
        profile="long",
        target_duration_s=300,
        segments=[EDLSegment(clip_id=1, trim_start_s=0.0, trim_end_s=10.0, order=0)],
    )
    argv = build_render_plan(edl, CLIPS, LONG, "/out/long.mp4")
    fc = filter_complex_of(argv)
    assert "scale=1920:1080:force_original_aspect_ratio=decrease" in fc
    assert "pad=1920:1080:(ow-iw)/2:(oh-ih)/2" in fc
    assert "concat=n=1:v=1:a=1[vc][ac]" in fc


def test_segments_rendered_in_order_field_order():
    edl = EDL(
        profile="short",
        target_duration_s=55,
        segments=[
            EDLSegment(clip_id=2, trim_start_s=0.0, trim_end_s=5.0, order=1),
            EDLSegment(clip_id=1, trim_start_s=1.0, trim_end_s=6.0, order=0),
        ],
    )
    argv = build_render_plan(edl, CLIPS, SHORT, "/out/f.mp4")
    assert argv.index("/clips/a.mp4") < argv.index("/clips/b.mp4")


def test_missing_clip_path_raises():
    clips = {1: ClipInfo(id=1, duration_s=10.0, category=None, score=0.5, clip_path=None)}
    edl = EDL(
        profile="short",
        target_duration_s=55,
        segments=[EDLSegment(clip_id=1, trim_start_s=0.0, trim_end_s=5.0, order=0)],
    )
    with pytest.raises(RenderError):
        build_render_plan(edl, clips, SHORT, "/out/f.mp4")
