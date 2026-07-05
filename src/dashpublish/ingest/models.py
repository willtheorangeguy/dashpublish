"""Dataclasses describing footage discovered on disk.

These are lightweight value objects produced by :mod:`dashpublish.ingest.discovery`
and consumed by :mod:`dashpublish.ingest.register`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

Camera = Literal["front", "back", "left_repeater", "right_repeater", "generic"]
SourceType = Literal["tesla_event", "generic"]


@dataclass(frozen=True)
class DiscoveredVideo:
    """A single video file found while walking a footage tree."""

    path: Path
    camera: Camera
    source_type: SourceType
    event_id: str | None
    recorded_at: datetime | None
    size_bytes: int


@dataclass(frozen=True)
class RegisterResult:
    """Summary returned by :func:`dashpublish.ingest.register.register_footage`."""

    new: int
    seen: int
    total: int
