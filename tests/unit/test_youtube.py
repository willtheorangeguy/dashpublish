"""Tests for dashpublish.youtube (auth, upload, publish, service orchestration)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import httplib2
import pytest
from googleapiclient.errors import HttpError

from dashpublish.config import Config, GeneralConfig
from dashpublish.db import repo
from dashpublish.testing import make_compilation, make_test_session
from dashpublish.youtube import auth as auth_mod
from dashpublish.youtube import upload as upload_mod
from dashpublish.youtube.auth import NotAuthenticatedError, get_credentials, is_authenticated
from dashpublish.youtube.publish import get_video_status, set_privacy
from dashpublish.youtube.service import CompilationNotReadyError, YouTubePublisher
from dashpublish.youtube.upload import UploadError, upload_video

# =========================================================================
# Helpers
# =========================================================================


class FakeCreds:
    """Stand-in for google.oauth2.credentials.Credentials (no network)."""

    def __init__(self, valid=True, expired=False, refresh_token=None, refresh_ok=True):
        self.valid = valid
        self.expired = expired
        self.refresh_token = refresh_token
        self.refresh_ok = refresh_ok
        self.refresh_calls: list = []

    def refresh(self, request):
        self.refresh_calls.append(request)
        if not self.refresh_ok:
            raise RuntimeError("refresh failed")
        self.valid = True
        self.expired = False

    def to_json(self):
        return json.dumps({"refresh_token": self.refresh_token or "rt", "token": "at"})


def _patch_token_loader(monkeypatch, creds: FakeCreds):
    class _Loader:
        @staticmethod
        def from_authorized_user_file(path, scopes):
            _Loader.loaded_from = (path, list(scopes))
            return creds

    monkeypatch.setattr(auth_mod, "Credentials", _Loader)
    monkeypatch.setattr(auth_mod, "Request", lambda: "fake-request")
    return _Loader


def _write_token(tokens_dir: Path, data: dict | str) -> Path:
    tokens_dir.mkdir(parents=True, exist_ok=True)
    token_path = tokens_dir / "youtube.json"
    text = data if isinstance(data, str) else json.dumps(data)
    token_path.write_text(text, encoding="utf-8")
    return token_path


def _http_error(status: int) -> HttpError:
    return HttpError(httplib2.Response({"status": str(status)}), b"boom")


class _FakeChunkStatus:
    def __init__(self, fraction: float):
        self._fraction = fraction

    def progress(self) -> float:
        return self._fraction


# =========================================================================
# auth
# =========================================================================


def test_get_credentials_returns_valid_saved_token(tmp_path, monkeypatch):
    tokens_dir = tmp_path / "tokens"
    _write_token(tokens_dir, {"refresh_token": "rt"})
    creds = FakeCreds(valid=True)
    loader = _patch_token_loader(monkeypatch, creds)

    result = get_credentials("secrets.json", tokens_dir)
    assert result is creds
    assert creds.refresh_calls == []
    assert loader.loaded_from[1] == auth_mod.SCOPES


def test_get_credentials_refreshes_expired_token_and_saves(tmp_path, monkeypatch):
    tokens_dir = tmp_path / "tokens"
    token_path = _write_token(tokens_dir, {"refresh_token": "rt"})
    creds = FakeCreds(valid=False, expired=True, refresh_token="rt")
    _patch_token_loader(monkeypatch, creds)

    result = get_credentials("secrets.json", tokens_dir, run_flow=False)
    assert result is creds
    assert creds.refresh_calls == ["fake-request"]
    # Refreshed token is written back to disk.
    assert json.loads(token_path.read_text(encoding="utf-8"))["refresh_token"] == "rt"


def test_get_credentials_no_token_run_flow_false_raises(tmp_path):
    with pytest.raises(NotAuthenticatedError):
        get_credentials("secrets.json", tmp_path / "tokens", run_flow=False)


def test_get_credentials_expired_without_refresh_token_raises(tmp_path, monkeypatch):
    tokens_dir = tmp_path / "tokens"
    _write_token(tokens_dir, {"token": "at"})
    creds = FakeCreds(valid=False, expired=True, refresh_token=None)
    _patch_token_loader(monkeypatch, creds)

    with pytest.raises(NotAuthenticatedError):
        get_credentials("secrets.json", tokens_dir, run_flow=False)


def test_get_credentials_runs_installed_app_flow(tmp_path, monkeypatch):
    tokens_dir = tmp_path / "tokens"
    flow_creds = FakeCreds(valid=True, refresh_token="new-rt")
    fake_flow = MagicMock()
    fake_flow.run_local_server.return_value = flow_creds
    flow_cls = MagicMock()
    flow_cls.from_client_secrets_file.return_value = fake_flow
    monkeypatch.setattr(auth_mod, "InstalledAppFlow", flow_cls)

    result = get_credentials("secrets.json", tokens_dir)
    assert result is flow_creds
    flow_cls.from_client_secrets_file.assert_called_once_with(
        "secrets.json", auth_mod.SCOPES
    )
    fake_flow.run_local_server.assert_called_once_with(port=0, open_browser=True)
    saved = json.loads((tokens_dir / "youtube.json").read_text(encoding="utf-8"))
    assert saved["refresh_token"] == "new-rt"


def test_is_authenticated(tmp_path):
    tokens_dir = tmp_path / "tokens"
    assert is_authenticated(tokens_dir) is False  # no file

    _write_token(tokens_dir, {"token": "at"})  # no refresh token
    assert is_authenticated(tokens_dir) is False

    _write_token(tokens_dir, "{not json")  # corrupt
    assert is_authenticated(tokens_dir) is False

    _write_token(tokens_dir, {"refresh_token": "rt"})
    assert is_authenticated(tokens_dir) is True


# =========================================================================
# upload
# =========================================================================


@pytest.fixture()
def video_file(tmp_path) -> str:
    path = tmp_path / "video.mp4"
    path.write_bytes(b"\x00" * 128)
    return str(path)


def _mock_service(next_chunk_side_effect):
    service = MagicMock()
    request = MagicMock()
    request.next_chunk.side_effect = next_chunk_side_effect
    service.videos.return_value.insert.return_value = request
    return service, request


def test_upload_body_privacy_and_truncation(video_file):
    service, _ = _mock_service([(None, {"id": "vid123"})])
    long_title = "T" * 150
    long_desc = "D" * 6000

    video_id = upload_video(
        service,
        file_path=video_file,
        title=long_title,
        description=long_desc,
        tags=["dashcam", "cars"],
        privacy="private",
        category_id="2",
    )
    assert video_id == "vid123"

    kwargs = service.videos.return_value.insert.call_args.kwargs
    assert kwargs["part"] == "snippet,status"
    body = kwargs["body"]
    assert body["snippet"]["title"] == "T" * 100
    assert body["snippet"]["description"] == "D" * 5000
    assert body["snippet"]["tags"] == ["dashcam", "cars"]
    assert body["snippet"]["categoryId"] == "2"
    assert body["status"]["privacyStatus"] == "private"
    assert body["status"]["selfDeclaredMadeForKids"] is False
    assert kwargs["media_body"] is not None


def test_upload_chunk_loop_and_progress(video_file):
    service, request = _mock_service(
        [
            (_FakeChunkStatus(0.25), None),
            (_FakeChunkStatus(0.5), None),
            (None, {"id": "abc"}),
        ]
    )
    fractions: list[float] = []

    video_id = upload_video(
        service,
        file_path=video_file,
        title="t",
        description="d",
        tags=[],
        progress_cb=fractions.append,
    )
    assert video_id == "abc"
    assert request.next_chunk.call_count == 3
    assert fractions == [0.25, 0.5, 1.0]


def test_upload_retries_5xx_then_succeeds(video_file, monkeypatch):
    monkeypatch.setattr(upload_mod.time, "sleep", lambda s: None)
    service, request = _mock_service([_http_error(503), (None, {"id": "abc"})])

    assert (
        upload_video(service, file_path=video_file, title="t", description="d", tags=[])
        == "abc"
    )
    assert request.next_chunk.call_count == 2


def test_upload_5xx_retries_exhausted_raises(video_file, monkeypatch):
    monkeypatch.setattr(upload_mod.time, "sleep", lambda s: None)
    service, request = _mock_service([_http_error(500)] * 4)

    with pytest.raises(UploadError):
        upload_video(service, file_path=video_file, title="t", description="d", tags=[])
    assert request.next_chunk.call_count == 4  # 1 attempt + 3 retries


def test_upload_non_retryable_error_raises_immediately(video_file):
    service, request = _mock_service([_http_error(403)])

    with pytest.raises(UploadError):
        upload_video(service, file_path=video_file, title="t", description="d", tags=[])
    assert request.next_chunk.call_count == 1


def test_upload_missing_video_id_raises(video_file):
    service, _ = _mock_service([(None, {})])
    with pytest.raises(UploadError):
        upload_video(service, file_path=video_file, title="t", description="d", tags=[])


# =========================================================================
# publish
# =========================================================================


def test_set_privacy_public_status_only():
    service = MagicMock()
    set_privacy(service, "vid123", "public")

    videos = service.videos.return_value
    videos.list.assert_not_called()
    kwargs = videos.update.call_args.kwargs
    assert kwargs["part"] == "status"
    assert kwargs["body"] == {"id": "vid123", "status": {"privacyStatus": "public"}}
    videos.update.return_value.execute.assert_called_once()


def test_set_privacy_snippet_merge_keeps_category_id():
    service = MagicMock()
    videos = service.videos.return_value
    videos.list.return_value.execute.return_value = {
        "items": [
            {
                "id": "vid123",
                "snippet": {
                    "title": "Old title",
                    "description": "Old desc",
                    "tags": ["old"],
                    "categoryId": "2",
                },
            }
        ]
    }

    set_privacy(service, "vid123", "public", title="New title", tags=["new"])

    videos.list.assert_called_once_with(part="snippet", id="vid123")
    kwargs = videos.update.call_args.kwargs
    assert kwargs["part"] == "status,snippet"
    snippet = kwargs["body"]["snippet"]
    assert snippet["title"] == "New title"
    assert snippet["tags"] == ["new"]
    assert snippet["categoryId"] == "2"  # preserved
    assert snippet["description"] == "Old desc"  # preserved
    assert kwargs["body"]["status"] == {"privacyStatus": "public"}


def test_set_privacy_snippet_update_missing_video_raises():
    service = MagicMock()
    service.videos.return_value.list.return_value.execute.return_value = {"items": []}
    with pytest.raises(ValueError):
        set_privacy(service, "nope", "public", title="x")


def test_get_video_status():
    service = MagicMock()
    service.videos.return_value.list.return_value.execute.return_value = {
        "items": [
            {
                "status": {"privacyStatus": "private"},
                "processingDetails": {"processingStatus": "succeeded"},
            }
        ]
    }
    assert get_video_status(service, "vid123") == {
        "privacyStatus": "private",
        "processingStatus": "succeeded",
    }
    service.videos.return_value.list.assert_called_once_with(
        part="status,processingDetails", id="vid123"
    )


# =========================================================================
# service (fake-mode end-to-end)
# =========================================================================


@pytest.fixture()
def fake_cfg(tmp_path) -> Config:
    return Config(
        general=GeneralConfig(data_dir=str(tmp_path / "data")),
        fake_mode=True,
    )


def _rendered_compilation(session, tmp_path):
    output = tmp_path / "comp.mp4"
    output.write_bytes(b"\x00" * 64)
    comp = make_compilation(session, status="rendered", output_path=str(output))
    session.commit()
    return comp


def test_upload_compilation_fake_end_to_end(fake_cfg, db_path, tmp_path):
    session = make_test_session(db_path)
    comp = _rendered_compilation(session, tmp_path)

    publisher = YouTubePublisher(fake_cfg, db_path)
    fractions: list[float] = []
    out = publisher.upload_compilation(
        comp.id,
        title="Best dashcam moments",
        description="Compilation",
        tags=["dashcam"],
        progress_cb=fractions.append,
    )

    assert out.youtube_video_id == "fake-yt-1"
    assert out.compilation_id == comp.id
    assert out.privacy_status == "private"  # cfg default
    assert out.uploaded_at is not None
    assert out.published_at is None
    assert fractions[-1] == 1.0

    # Fake recorded the real insert body (same production code path).
    insert_body = publisher.fake.insert_calls[0]["body"]
    assert insert_body["snippet"]["title"] == "Best dashcam moments"
    assert insert_body["snippet"]["categoryId"] == "2"
    assert insert_body["status"]["privacyStatus"] == "private"
    assert insert_body["status"]["selfDeclaredMadeForKids"] is False

    session.expire_all()
    assert repo.get_compilation(session, comp.id).status == "uploaded"
    records = repo.list_publish_records(session, compilation_id=comp.id)
    assert [r.id for r in records] == [out.id]
    session.close()


def test_publish_fake_flips_to_public(fake_cfg, db_path, tmp_path):
    session = make_test_session(db_path)
    comp = _rendered_compilation(session, tmp_path)

    publisher = YouTubePublisher(fake_cfg, db_path)
    record = publisher.upload_compilation(comp.id, title="t", description="", tags=[])
    published = publisher.publish(record.id)

    assert published.id == record.id
    assert published.privacy_status == "public"
    assert published.published_at is not None

    update = publisher.fake.update_calls[0]
    assert update["part"] == "status"
    assert update["body"]["status"]["privacyStatus"] == "public"
    assert publisher.fake.videos_store["fake-yt-1"]["status"]["privacyStatus"] == "public"

    session.expire_all()
    assert repo.get_compilation(session, comp.id).status == "published"
    session.close()


def test_upload_non_rendered_compilation_raises(fake_cfg, db_path):
    session = make_test_session(db_path)
    comp = make_compilation(session, status="draft")
    session.commit()

    publisher = YouTubePublisher(fake_cfg, db_path)
    with pytest.raises(CompilationNotReadyError):
        publisher.upload_compilation(comp.id, title="t", description="", tags=[])
    session.close()


def test_upload_missing_output_file_raises(fake_cfg, db_path, tmp_path):
    session = make_test_session(db_path)
    comp = make_compilation(
        session, status="rendered", output_path=str(tmp_path / "missing.mp4")
    )
    session.commit()

    publisher = YouTubePublisher(fake_cfg, db_path)
    with pytest.raises(CompilationNotReadyError):
        publisher.upload_compilation(comp.id, title="t", description="", tags=[])
    session.close()


def test_upload_unknown_compilation_raises(fake_cfg, db_path):
    make_test_session(db_path).close()
    publisher = YouTubePublisher(fake_cfg, db_path)
    with pytest.raises(ValueError):
        publisher.upload_compilation(999, title="t", description="", tags=[])


def test_auth_status(tmp_path, db_path):
    fake = Config(general=GeneralConfig(data_dir=str(tmp_path / "d1")), fake_mode=True)
    assert YouTubePublisher(fake, db_path).auth_status() is True

    real = Config(general=GeneralConfig(data_dir=str(tmp_path / "d2")), fake_mode=False)
    publisher = YouTubePublisher(real, db_path)
    assert publisher.auth_status() is False
    _write_token(Path(tmp_path / "d2") / "tokens", {"refresh_token": "rt"})
    assert publisher.auth_status() is True
