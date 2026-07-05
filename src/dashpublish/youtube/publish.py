"""Post-upload video management: flip privacy, edit metadata, poll status."""

from __future__ import annotations


def set_privacy(
    service,
    video_id: str,
    privacy: str = "public",
    *,
    title: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
) -> None:
    """Update a video's privacy status (and optionally its snippet metadata).

    A snippet update on the YouTube API *replaces* the snippet and requires ``title``
    and ``categoryId``, so when any metadata field is provided we first fetch the
    current snippet, merge the changes in, and keep the existing ``categoryId``.
    """
    parts = ["status"]
    body: dict = {"id": video_id, "status": {"privacyStatus": privacy}}

    if title is not None or description is not None or tags is not None:
        listing = (
            service.videos().list(part="snippet", id=video_id).execute()
        )
        items = listing.get("items") or []
        if not items:
            raise ValueError(f"YouTube video not found: {video_id}")
        snippet = dict(items[0].get("snippet") or {})
        if title is not None:
            snippet["title"] = title
        if description is not None:
            snippet["description"] = description
        if tags is not None:
            snippet["tags"] = list(tags)
        body["snippet"] = snippet
        parts.append("snippet")

    service.videos().update(part=",".join(parts), body=body).execute()


def get_video_status(service, video_id: str) -> dict:
    """Return ``{"privacyStatus": ..., "processingStatus": ...}`` for a video."""
    listing = (
        service.videos().list(part="status,processingDetails", id=video_id).execute()
    )
    items = listing.get("items") or []
    if not items:
        return {"privacyStatus": None, "processingStatus": None}
    item = items[0]
    return {
        "privacyStatus": (item.get("status") or {}).get("privacyStatus"),
        "processingStatus": (item.get("processingDetails") or {}).get(
            "processingStatus"
        ),
    }
