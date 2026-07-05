"""High-level YouTube orchestration used by the API routes and the CLI.

:class:`YouTubePublisher` ties the low-level pieces together: it validates the
compilation, uploads via :func:`dashpublish.youtube.upload.upload_video`, records the
result in ``publish_records``, and flips statuses on publish.

Fake seam
---------
When ``cfg.fake_mode`` is set, :class:`YouTubePublisher` swaps the *service object* for
:class:`FakeYouTube`, an in-memory stand-in that mimics the minimal googleapiclient
surface used by this package (``videos().insert(...).next_chunk()``,
``videos().update(...).execute()``, ``videos().list(...).execute()``). Everything above
that seam — metadata truncation, request bodies, DB writes, status transitions — runs
through the exact same production code paths, and the fake records every call for
assertions. Fake uploads get sequential ids ``fake-yt-1``, ``fake-yt-2``, ...
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from dashpublish.config import Config
from dashpublish.db import repo
from dashpublish.db.engine import session_scope
from dashpublish.db.models import PublishRecord, utcnow
from dashpublish.db.schemas import PublishRecordOut
from dashpublish.paths import resolve_paths
from dashpublish.youtube.auth import build_service, get_credentials, is_authenticated
from dashpublish.youtube.publish import set_privacy
from dashpublish.youtube.upload import upload_video


class CompilationNotReadyError(RuntimeError):
    """The compilation is not in a state that allows the requested operation."""


# =========================================================================
# FakeYouTube — offline stand-in for the googleapiclient service resource
# =========================================================================
class _FakeInsertRequest:
    def __init__(self, fake: "FakeYouTube", body: dict) -> None:
        self._fake = fake
        self._body = body

    def next_chunk(self):
        fake = self._fake
        fake.upload_counter += 1
        video_id = f"fake-yt-{fake.upload_counter}"
        fake.videos_store[video_id] = {
            "snippet": dict(self._body.get("snippet") or {}),
            "status": dict(self._body.get("status") or {}),
            "processingDetails": {"processingStatus": "succeeded"},
        }
        return None, {"id": video_id}


class _FakeExecutable:
    def __init__(self, result: dict) -> None:
        self._result = result

    def execute(self) -> dict:
        return self._result


class _FakeVideos:
    def __init__(self, fake: "FakeYouTube") -> None:
        self._fake = fake

    def insert(self, *, part: str, body: dict, media_body=None) -> _FakeInsertRequest:
        self._fake.insert_calls.append(
            {"part": part, "body": body, "media_body": media_body}
        )
        return _FakeInsertRequest(self._fake, body)

    def update(self, *, part: str, body: dict) -> _FakeExecutable:
        self._fake.update_calls.append({"part": part, "body": body})
        video_id = body.get("id")
        stored = self._fake.videos_store.get(video_id)
        if stored is not None:
            if "status" in body:
                stored["status"].update(body["status"])
            if "snippet" in body:
                stored["snippet"] = dict(body["snippet"])
        return _FakeExecutable(dict(body))

    def list(self, *, part: str, id: str) -> _FakeExecutable:
        self._fake.list_calls.append({"part": part, "id": id})
        items = []
        stored = self._fake.videos_store.get(id)
        if stored is not None:
            items.append({"id": id, **{k: dict(v) for k, v in stored.items()}})
        return _FakeExecutable({"items": items})


class FakeYouTube:
    """In-memory fake of the googleapiclient YouTube resource (minimal surface).

    Records ``insert_calls`` / ``update_calls`` / ``list_calls`` and keeps uploaded
    videos in ``videos_store`` so privacy flips and snippet merges behave like the
    real API.
    """

    def __init__(self) -> None:
        self.upload_counter = 0
        self.videos_store: dict[str, dict] = {}
        self.insert_calls: list[dict] = []
        self.update_calls: list[dict] = []
        self.list_calls: list[dict] = []

    def videos(self) -> _FakeVideos:
        return _FakeVideos(self)


# =========================================================================
# YouTubePublisher
# =========================================================================
class YouTubePublisher:
    """Upload rendered compilations to YouTube and publish them.

    In fake mode (``cfg.fake_mode``) a :class:`FakeYouTube` service is used and no
    network or OAuth is touched. A pre-built service can also be injected via
    ``service`` (used by tests and by callers that manage credentials themselves).
    """

    def __init__(self, cfg: Config, db_path: str | Path, *, service=None) -> None:
        self.cfg = cfg
        self.db_path = db_path
        self.fake: FakeYouTube | None = None
        self._service = service
        if service is None and cfg.fake_mode:
            self.fake = FakeYouTube()
            self._service = self.fake

    def _get_service(self):
        if self._service is None:
            tokens_dir = resolve_paths(self.cfg).tokens_dir
            credentials = get_credentials(
                self.cfg.youtube_client_secrets or "", tokens_dir, run_flow=False
            )
            self._service = build_service(credentials)
        return self._service

    def auth_status(self) -> bool:
        """True when uploads can proceed without interactive auth."""
        if self.cfg.fake_mode or self._service is not None:
            return True
        return is_authenticated(resolve_paths(self.cfg).tokens_dir)

    def upload_compilation(
        self,
        compilation_id: int,
        *,
        title: str,
        description: str = "",
        tags: list[str] | None = None,
        progress_cb: Callable[[float], None] | None = None,
    ) -> PublishRecordOut:
        """Upload a rendered compilation with the configured default privacy.

        Creates a ``publish_records`` row (with ``uploaded_at``) and moves the
        compilation to status ``uploaded``. The compilation must be in status
        ``rendered`` with an existing ``output_path``.
        """
        with session_scope(self.db_path) as session:
            comp = repo.get_compilation(session, compilation_id)
            if comp is None:
                raise ValueError(f"Compilation {compilation_id} not found")
            if comp.status != "rendered":
                raise CompilationNotReadyError(
                    f"Compilation {compilation_id} is '{comp.status}', expected 'rendered'"
                )
            if not comp.output_path or not Path(comp.output_path).exists():
                raise CompilationNotReadyError(
                    f"Compilation {compilation_id} has no rendered output file "
                    f"({comp.output_path!r})"
                )
            output_path = comp.output_path

        privacy = self.cfg.youtube.default_privacy
        tag_list = list(tags or [])
        video_id = upload_video(
            self._get_service(),
            file_path=output_path,
            title=title,
            description=description,
            tags=tag_list,
            privacy=privacy,
            category_id=self.cfg.youtube.category_id,
            progress_cb=progress_cb,
        )

        with session_scope(self.db_path) as session:
            record = repo.create_publish_record(
                session,
                compilation_id=compilation_id,
                privacy_status=privacy,
                title=title,
                description=description,
                tags_json=tag_list,
                youtube_video_id=video_id,
            )
            repo.update_publish_record(session, record.id, uploaded_at=utcnow())
            repo.update_compilation(session, compilation_id, status="uploaded")
            return PublishRecordOut.model_validate(record)

    def publish(self, publish_record_id: int) -> PublishRecordOut:
        """Flip an uploaded video to public and mark the compilation published."""
        with session_scope(self.db_path) as session:
            record = session.get(PublishRecord, publish_record_id)
            if record is None:
                raise ValueError(f"Publish record {publish_record_id} not found")
            if not record.youtube_video_id:
                raise CompilationNotReadyError(
                    f"Publish record {publish_record_id} has no YouTube video id"
                )
            video_id = record.youtube_video_id
            compilation_id = record.compilation_id

        set_privacy(self._get_service(), video_id, "public")

        with session_scope(self.db_path) as session:
            record = repo.update_publish_record(
                session,
                publish_record_id,
                privacy_status="public",
                published_at=utcnow(),
            )
            repo.update_compilation(session, compilation_id, status="published")
            return PublishRecordOut.model_validate(record)
