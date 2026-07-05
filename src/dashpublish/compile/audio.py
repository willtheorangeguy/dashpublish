"""Background-music filtergraph: loop, duck under clip audio, mix."""

from __future__ import annotations


def build_music_filter(
    music_input_index: int,
    concat_audio_label: str,
    total_duration_s: float,
    duck_db: float,
) -> tuple[list[str], str]:
    """Return ``(filter_parts, output_label)`` for the music-ducking chain.

    The chain:

    1. splits the concatenated clip audio (it feeds both the sidechain key and
       the final mix — a labelled stream cannot be consumed twice),
    2. attenuates the music by ``duck_db`` dB, loops it, and trims it to the
       compilation length,
    3. sidechain-compresses the music against the clip audio (ducks music when
       clips are loud),
    4. mixes clip audio + ducked music into ``[aout]``.
    """
    return (
        [
            f"[{concat_audio_label}]asplit=2[acmain][ackey]",
            (
                f"[{music_input_index}:a]volume={duck_db:g}dB,"
                f"aloop=loop=-1:size=2e9,atrim=0:{total_duration_s:.3f}[bg]"
            ),
            "[bg][ackey]sidechaincompress="
            "threshold=0.05:ratio=8:attack=20:release=500:makeup=1[bgd]",
            "[acmain][bgd]amix=inputs=2:duration=first:normalize=0[aout]",
        ],
        "aout",
    )
