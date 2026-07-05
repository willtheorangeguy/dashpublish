"""Footage discovery and registration (Package B)."""

from dashpublish.ingest.discovery import discover_videos
from dashpublish.ingest.models import DiscoveredVideo, RegisterResult
from dashpublish.ingest.register import register_footage

__all__ = [
    "DiscoveredVideo",
    "RegisterResult",
    "discover_videos",
    "register_footage",
]
