"""Output profiles for compilation rendering (short 9:16, long 16:9)."""

from __future__ import annotations

from dataclasses import dataclass

from dashpublish.config import Config, load_config

SHORT_VF_CHAIN = "crop=ih*9/16:ih,scale=1080:1920,setsar=1,fps=30"
LONG_VF_CHAIN = (
    "scale=1920:1080:force_original_aspect_ratio=decrease,"
    "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30"
)

LONG_MAX_DURATION_S = 900


@dataclass(frozen=True)
class Profile:
    """Rendering profile: output geometry, duration budget, per-segment filter."""

    name: str  # "short" | "long"
    width: int
    height: int
    max_duration_s: int
    target_duration_s: int
    min_segment_s: float
    max_segment_s: float
    vf_chain: str  # per-segment video filter string


def get_profile(name: str, cfg: Config | None = None) -> Profile:
    """Return the :class:`Profile` for ``name`` ("short" or "long")."""
    cfg = cfg or load_config()
    if name == "short":
        max_s = cfg.compile.short_max_s
        return Profile(
            name="short",
            width=1080,
            height=1920,
            max_duration_s=max_s,
            target_duration_s=min(55, max_s),
            min_segment_s=2.0,
            max_segment_s=10.0,
            vf_chain=SHORT_VF_CHAIN,
        )
    if name == "long":
        return Profile(
            name="long",
            width=1920,
            height=1080,
            max_duration_s=LONG_MAX_DURATION_S,
            target_duration_s=cfg.compile.long_target_s,
            min_segment_s=4.0,
            max_segment_s=30.0,
            vf_chain=LONG_VF_CHAIN,
        )
    raise ValueError(f"unknown profile: {name!r} (expected 'short' or 'long')")
