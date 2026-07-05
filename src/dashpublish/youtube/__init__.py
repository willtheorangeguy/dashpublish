"""YouTube integration: OAuth, resumable upload, publish, and orchestration."""

from dashpublish.youtube.auth import (
    SCOPES,
    NotAuthenticatedError,
    build_service,
    get_credentials,
    is_authenticated,
)
from dashpublish.youtube.publish import get_video_status, set_privacy
from dashpublish.youtube.service import (
    CompilationNotReadyError,
    FakeYouTube,
    YouTubePublisher,
)
from dashpublish.youtube.upload import UploadError, upload_video

__all__ = [
    "SCOPES",
    "NotAuthenticatedError",
    "build_service",
    "get_credentials",
    "is_authenticated",
    "get_video_status",
    "set_privacy",
    "CompilationNotReadyError",
    "FakeYouTube",
    "YouTubePublisher",
    "UploadError",
    "upload_video",
]
