"""Gemini provider via the ``google-genai`` SDK (structured JSON output)."""

from __future__ import annotations

import json
from typing import Any

from dashpublish.llm._json import RETRY_INSTRUCTION, SchemaMismatchError, parse_json_object
from dashpublish.llm.errors import LLMError


class GeminiProvider:
    """LLMProvider backed by the Gemini API.

    ``chat_json`` uses structured output (``response_mime_type`` +
    ``response_schema``) and retries once with a corrective user turn when the
    model returns invalid JSON, then raises :class:`LLMError`.

    A pre-built ``client`` may be injected for tests; otherwise a
    ``google.genai.Client`` is created from ``api_key``.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        *,
        client: Any | None = None,
    ) -> None:
        self.model = model
        if client is None:
            from google import genai

            client = genai.Client(api_key=api_key)
        self._client = client

    def chat_json(self, system: str, user: str, schema: dict) -> dict:
        contents: list[str] = [user]
        last_error: Exception | None = None
        for _attempt in range(2):
            response = self._client.models.generate_content(
                model=self.model,
                contents=contents if len(contents) > 1 else contents[0],
                config={
                    "response_mime_type": "application/json",
                    "response_schema": schema,
                    "system_instruction": system,
                },
            )
            text = response.text or ""
            try:
                return parse_json_object(text, schema)
            except (json.JSONDecodeError, SchemaMismatchError) as exc:
                last_error = exc
                contents = [user, RETRY_INSTRUCTION]
        raise LLMError(
            f"Gemini returned invalid JSON for the requested schema after retry: {last_error}"
        )

    def complete(self, prompt: str) -> str:
        response = self._client.models.generate_content(
            model=self.model,
            contents=prompt,
            config={},
        )
        return response.text or ""
