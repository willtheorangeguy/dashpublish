"""YouTube OAuth: installed-app flow, token persistence, and auto-refresh.

The OAuth token is stored as JSON at ``<tokens_dir>/youtube.json``. ``dashpublish init``
runs the browser flow once; afterwards :func:`get_credentials` silently refreshes the
token when it expires. Non-interactive callers (API server, worker) pass
``run_flow=False`` and get :class:`NotAuthenticatedError` instead of a browser popup.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES: list[str] = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

TOKEN_FILENAME = "youtube.json"


class NotAuthenticatedError(RuntimeError):
    """No valid YouTube credentials and interactive auth was not allowed."""


def _token_path(tokens_dir: str | Path) -> Path:
    return Path(tokens_dir) / TOKEN_FILENAME


def _save_token(token_path: Path, credentials: Credentials) -> None:
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(credentials.to_json(), encoding="utf-8")


def get_credentials(
    client_secrets_path: str,
    tokens_dir: Path,
    *,
    scopes: Sequence[str] = SCOPES,
    run_flow: bool = True,
) -> Credentials:
    """Return valid YouTube OAuth credentials.

    Order: load saved token -> refresh if expired -> (optionally) run the
    installed-app browser flow. The token file is (re)written whenever new or
    refreshed credentials are obtained.

    Raises :class:`NotAuthenticatedError` if no valid credentials can be obtained
    and ``run_flow`` is False (or no client secrets file is configured).
    """
    scope_list = list(scopes)
    token_path = _token_path(tokens_dir)

    creds: Credentials | None = None
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), scope_list)
        except (ValueError, KeyError):
            creds = None

    if creds is not None and creds.valid:
        return creds

    refreshed = False
    if creds is not None and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            refreshed = creds.valid
        except Exception:
            refreshed = False

    if not refreshed:
        if not run_flow:
            raise NotAuthenticatedError(
                "No valid YouTube token; run `dashpublish init` to authenticate."
            )
        if not client_secrets_path:
            raise NotAuthenticatedError(
                "YOUTUBE_CLIENT_SECRETS is not set; cannot run the OAuth flow."
            )
        flow = InstalledAppFlow.from_client_secrets_file(client_secrets_path, scope_list)
        creds = flow.run_local_server(port=0, open_browser=True)

    _save_token(token_path, creds)
    return creds


def is_authenticated(tokens_dir: str | Path) -> bool:
    """True if a saved token with a refresh token exists. No network calls."""
    token_path = _token_path(tokens_dir)
    if not token_path.exists():
        return False
    try:
        data = json.loads(token_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and bool(data.get("refresh_token"))


def build_service(credentials: Credentials):
    """Build the YouTube Data API v3 service resource."""
    return build("youtube", "v3", credentials=credentials, cache_discovery=False)
