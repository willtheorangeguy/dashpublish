"""Provider factory: pick the configured LLM backend (or a fake in fake mode)."""

from __future__ import annotations

import re

from dashpublish.config import Config
from dashpublish.llm.base import FakeProvider, LLMProvider
from dashpublish.llm.errors import LLMError
from dashpublish.llm.gemini import GeminiProvider
from dashpublish.llm.ollama import OllamaProvider


class PlanningFakeProvider(FakeProvider):
    """FakeProvider that synthesizes sensible EDL / metadata responses.

    When explicit canned ``responses`` are given it behaves exactly like
    :class:`FakeProvider`. Otherwise it inspects the requested schema:

    - EDL schema (has "segments"): builds segments from the candidate clip ids
      and durations embedded in the user prompt (the prompt format is owned by
      :mod:`dashpublish.llm.prompts`), so fake-mode plans always reference real
      clips.
    - Metadata schema (has "title"): returns deterministic title/description/tags.
    """

    def chat_json(self, system: str, user: str, schema: dict) -> dict:
        if self.responses:
            return super().chat_json(system, user, schema)
        self.calls.append({"system": system, "user": user, "schema": schema})
        properties = (schema or {}).get("properties", {})
        if "segments" in properties:
            return self._fake_edl(user)
        if "title" in properties:
            return {
                "title": "Wildest Dashcam Moments Compilation #Shorts",
                "description": (
                    "The best dashcam clips in one compilation.\n\n"
                    "#dashcam #driving #Shorts"
                ),
                "tags": ["dashcam", "compilation", "driving", "near miss", "road rage"],
            }
        return {}

    @staticmethod
    def _fake_edl(user: str) -> dict:
        profile = "short" if '"short"' in user else "long"
        ids = [int(m) for m in re.findall(r'"id":\s*(\d+)', user)]
        durations = [float(m) for m in re.findall(r'"duration_s":\s*([\d.]+)', user)]
        segments = []
        for order, clip_id in enumerate(ids[:8]):
            duration = durations[order] if order < len(durations) else 5.0
            segments.append(
                {
                    "clip_id": clip_id,
                    "trim_start_s": 0,
                    "trim_end_s": min(duration, 8.0),
                    "order": order,
                }
            )
        if not segments:
            segments = [{"clip_id": 1, "trim_start_s": 0, "trim_end_s": 5.0, "order": 0}]
        return {
            "profile": profile,
            "target_duration_s": 55 if profile == "short" else 300,
            "segments": segments,
            "transition": "cut",
            "rationale": "fake-mode deterministic plan",
        }


def get_provider(cfg: Config) -> LLMProvider:
    """Return the configured LLM provider.

    ``fake_mode`` wins over everything and returns a :class:`PlanningFakeProvider`.
    """
    if cfg.fake_mode:
        return PlanningFakeProvider()
    if cfg.llm.provider == "gemini":
        if not cfg.gemini_api_key:
            raise LLMError(
                "Gemini provider selected but no API key found. "
                "Set the GEMINI_API_KEY environment variable, or switch "
                '[llm].provider to "ollama" in dashpublish.toml.'
            )
        return GeminiProvider(api_key=cfg.gemini_api_key, model=cfg.llm.model)
    if cfg.llm.provider == "ollama":
        return OllamaProvider(cfg.llm.ollama_url, cfg.llm.ollama_model)
    raise LLMError(f"unknown LLM provider: {cfg.llm.provider!r}")
