"""Shared helpers for parsing and lightly validating provider JSON output."""

from __future__ import annotations

import json

RETRY_INSTRUCTION = (
    "Your previous output was invalid JSON for the schema; output ONLY valid JSON."
)


class SchemaMismatchError(ValueError):
    """The output parsed as JSON but does not match the requested schema."""


def parse_json_object(text: str, schema: dict) -> dict:
    """Parse ``text`` as a JSON object and check top-level required keys.

    Raises ``json.JSONDecodeError`` on malformed JSON and
    :class:`SchemaMismatchError` when the value is not an object or is missing
    a top-level ``required`` key from ``schema``. Full JSON-schema validation is
    intentionally out of scope — downstream Pydantic models enforce the rest.
    """
    data = json.loads(text)
    if not isinstance(data, dict):
        raise SchemaMismatchError("top-level JSON value is not an object")
    for key in schema.get("required", []):
        if key not in data:
            raise SchemaMismatchError(f"missing required key: {key!r}")
    return data
