"""Filesystem path resolution for dashpublish runtime data.

Given a :class:`~dashpublish.config.Config`, resolve the data directory and its
sub-directories (creating them on demand).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dashpublish.config import Config


@dataclass(frozen=True)
class Paths:
    """Resolved runtime paths. All directories are created when this is built."""

    data_dir: Path
    db_path: Path
    clips_dir: Path
    compilations_dir: Path
    thumbs_dir: Path
    tokens_dir: Path
    music_dir: Path


def resolve_paths(config: Config) -> Paths:
    """Resolve and create the data directory tree for the given config."""
    data_dir = Path(config.general.data_dir).expanduser().resolve()
    clips_dir = data_dir / "clips"
    compilations_dir = data_dir / "compilations"
    thumbs_dir = data_dir / "thumbs"
    tokens_dir = data_dir / "tokens"
    music_dir = data_dir / "music"

    for directory in (
        data_dir,
        clips_dir,
        compilations_dir,
        thumbs_dir,
        tokens_dir,
        music_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    return Paths(
        data_dir=data_dir,
        db_path=data_dir / "db.sqlite",
        clips_dir=clips_dir,
        compilations_dir=compilations_dir,
        thumbs_dir=thumbs_dir,
        tokens_dir=tokens_dir,
        music_dir=music_dir,
    )
