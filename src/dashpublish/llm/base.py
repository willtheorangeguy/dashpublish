"""LLM provider protocol and a fake implementation for tests/dry-run.

Real providers (Gemini, Ollama) are implemented in Package C.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """A creative-LLM backend."""

    def chat_json(self, system: str, user: str, schema: dict) -> dict:
        """Return a JSON object conforming to ``schema``."""
        ...

    def complete(self, prompt: str) -> str:
        """Return a plain-text completion."""
        ...


class FakeProvider:
    """Deterministic fake LLM.

    Pass ``responses`` — a list of dicts. ``chat_json`` pops them in order and repeats
    the last one once exhausted. With no responses it echoes an empty object.
    ``complete`` returns ``text`` (default echoes the prompt).
    """

    def __init__(
        self,
        responses: list[dict] | None = None,
        text: str | None = None,
    ) -> None:
        self.responses: list[dict] = list(responses or [])
        self._text = text
        self.calls: list[dict[str, Any]] = []

    def chat_json(self, system: str, user: str, schema: dict) -> dict:
        self.calls.append({"system": system, "user": user, "schema": schema})
        if not self.responses:
            return {}
        if len(self.responses) == 1:
            return dict(self.responses[0])
        return dict(self.responses.pop(0))

    def complete(self, prompt: str) -> str:
        self.calls.append({"prompt": prompt})
        if self._text is not None:
            return self._text
        return prompt
