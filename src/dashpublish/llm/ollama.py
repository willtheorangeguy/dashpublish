"""Ollama provider via the local ``/api/chat`` HTTP endpoint."""

from __future__ import annotations

import json

import httpx

from dashpublish.llm._json import RETRY_INSTRUCTION, SchemaMismatchError, parse_json_object
from dashpublish.llm.errors import LLMError

DEFAULT_TIMEOUT_S = 300.0


class OllamaProvider:
    """LLMProvider backed by a local Ollama server.

    ``chat_json`` posts to ``{base_url}/api/chat`` with ``format`` set to the
    JSON schema (Ollama constrains decoding to it) and ``stream: false``.
    Invalid JSON output is retried once with a corrective user turn, then
    :class:`LLMError` is raised.

    A custom ``transport`` may be injected for tests (httpx.MockTransport).
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_S,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def _chat(self, messages: list[dict], schema: dict) -> str:
        response = self._client.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "format": schema,
                "stream": False,
            },
        )
        response.raise_for_status()
        return response.json().get("message", {}).get("content", "")

    def chat_json(self, system: str, user: str, schema: dict) -> dict:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        last_error: Exception | None = None
        for _attempt in range(2):
            content = self._chat(messages, schema)
            try:
                return parse_json_object(content, schema)
            except (json.JSONDecodeError, SchemaMismatchError) as exc:
                last_error = exc
                messages = messages + [
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": RETRY_INSTRUCTION},
                ]
        raise LLMError(
            f"Ollama returned invalid JSON for the requested schema after retry: {last_error}"
        )

    def complete(self, prompt: str) -> str:
        response = self._client.post(
            f"{self.base_url}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False},
        )
        response.raise_for_status()
        return response.json().get("response", "")
