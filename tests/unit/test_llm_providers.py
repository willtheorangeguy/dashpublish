"""Provider tests: Ollama (MockTransport), Gemini (fake client), factory."""

from __future__ import annotations

import json

import httpx
import pytest

from dashpublish.config import Config, LLMConfig
from dashpublish.llm._json import RETRY_INSTRUCTION
from dashpublish.llm.base import FakeProvider
from dashpublish.llm.errors import LLMError
from dashpublish.llm.factory import PlanningFakeProvider, get_provider
from dashpublish.llm.gemini import GeminiProvider
from dashpublish.llm.ollama import OllamaProvider

SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "integer"}},
    "required": ["answer"],
}


# =========================================================================
# Ollama
# =========================================================================
def make_ollama(contents: list[str]) -> tuple[OllamaProvider, list[dict]]:
    """Ollama provider whose /api/chat returns each of ``contents`` in turn."""
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append({"url": str(request.url), "payload": payload})
        content = contents[min(len(requests) - 1, len(contents) - 1)]
        return httpx.Response(200, json={"message": {"role": "assistant", "content": content}})

    provider = OllamaProvider(
        "http://ollama.test", "llama3.1", transport=httpx.MockTransport(handler)
    )
    return provider, requests


def test_ollama_chat_json_success():
    provider, requests = make_ollama(['{"answer": 42}'])
    result = provider.chat_json("sys", "user msg", SCHEMA)
    assert result == {"answer": 42}
    assert len(requests) == 1
    payload = requests[0]["payload"]
    assert requests[0]["url"] == "http://ollama.test/api/chat"
    assert payload["model"] == "llama3.1"
    assert payload["format"] == SCHEMA
    assert payload["stream"] is False
    assert payload["messages"][0] == {"role": "system", "content": "sys"}
    assert payload["messages"][1] == {"role": "user", "content": "user msg"}


def test_ollama_retries_once_on_invalid_json():
    provider, requests = make_ollama(["not json at all", '{"answer": 7}'])
    result = provider.chat_json("sys", "user", SCHEMA)
    assert result == {"answer": 7}
    assert len(requests) == 2
    retry_messages = requests[1]["payload"]["messages"]
    assert retry_messages[-1] == {"role": "user", "content": RETRY_INSTRUCTION}
    assert retry_messages[-2]["role"] == "assistant"


def test_ollama_retries_on_schema_mismatch():
    provider, requests = make_ollama(['{"wrong_key": 1}', '{"answer": 3}'])
    assert provider.chat_json("sys", "user", SCHEMA) == {"answer": 3}
    assert len(requests) == 2


def test_ollama_raises_llm_error_after_retry():
    provider, requests = make_ollama(["garbage", "more garbage"])
    with pytest.raises(LLMError):
        provider.chat_json("sys", "user", SCHEMA)
    assert len(requests) == 2


def test_ollama_complete():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).endswith("/api/generate")
        return httpx.Response(200, json={"response": "hello"})

    provider = OllamaProvider(
        "http://ollama.test/", "llama3.1", transport=httpx.MockTransport(handler)
    )
    assert provider.complete("hi") == "hello"


# =========================================================================
# Gemini (fake genai client)
# =========================================================================
class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeModels:
    def __init__(self, texts: list[str]) -> None:
        self.texts = list(texts)
        self.calls: list[dict] = []

    def generate_content(self, *, model: str, contents, config) -> _FakeResponse:
        self.calls.append({"model": model, "contents": contents, "config": config})
        text = self.texts.pop(0) if len(self.texts) > 1 else self.texts[0]
        return _FakeResponse(text)


class _FakeClient:
    def __init__(self, texts: list[str]) -> None:
        self.models = _FakeModels(texts)


def make_gemini(texts: list[str]) -> tuple[GeminiProvider, _FakeModels]:
    client = _FakeClient(texts)
    return GeminiProvider("key", "gemini-2.5-flash", client=client), client.models


def test_gemini_chat_json_success():
    provider, models = make_gemini(['{"answer": 1}'])
    assert provider.chat_json("sys", "user", SCHEMA) == {"answer": 1}
    assert len(models.calls) == 1
    call = models.calls[0]
    assert call["model"] == "gemini-2.5-flash"
    assert call["contents"] == "user"
    assert call["config"]["response_mime_type"] == "application/json"
    assert call["config"]["response_schema"] == SCHEMA
    assert call["config"]["system_instruction"] == "sys"


def test_gemini_retries_once_on_invalid_json():
    provider, models = make_gemini(["```not json```", '{"answer": 2}'])
    assert provider.chat_json("sys", "user", SCHEMA) == {"answer": 2}
    assert len(models.calls) == 2
    assert models.calls[1]["contents"] == ["user", RETRY_INSTRUCTION]


def test_gemini_raises_llm_error_after_retry():
    provider, models = make_gemini(["nope"])
    with pytest.raises(LLMError):
        provider.chat_json("sys", "user", SCHEMA)
    assert len(models.calls) == 2


def test_gemini_complete():
    provider, _ = make_gemini(["plain text"])
    assert provider.complete("prompt") == "plain text"


# =========================================================================
# Factory
# =========================================================================
def test_factory_fake_mode_wins():
    cfg = Config(fake_mode=True, llm=LLMConfig(provider="gemini"))
    provider = get_provider(cfg)
    assert isinstance(provider, FakeProvider)
    assert isinstance(provider, PlanningFakeProvider)


def test_factory_fake_provider_synthesizes_valid_edl():
    from dashpublish.compile.edl import edl_json_schema

    provider = get_provider(Config(fake_mode=True))
    user = '- profile: "short"\n[{"id": 4, "score": 0.9, "duration_s": 6.0}]'
    result = provider.chat_json("sys", user, edl_json_schema())
    assert result["profile"] == "short"
    assert result["segments"][0]["clip_id"] == 4
    assert result["segments"][0]["trim_end_s"] == pytest.approx(6.0)


def test_factory_gemini_requires_api_key():
    cfg = Config(llm=LLMConfig(provider="gemini"), gemini_api_key=None)
    with pytest.raises(LLMError, match="GEMINI_API_KEY"):
        get_provider(cfg)


def test_factory_gemini_with_key():
    cfg = Config(llm=LLMConfig(provider="gemini", model="gemini-2.5-flash"), gemini_api_key="k")
    provider = get_provider(cfg)
    assert isinstance(provider, GeminiProvider)
    assert provider.model == "gemini-2.5-flash"


def test_factory_ollama():
    cfg = Config(
        llm=LLMConfig(provider="ollama", ollama_url="http://box:11434", ollama_model="qwen3")
    )
    provider = get_provider(cfg)
    assert isinstance(provider, OllamaProvider)
    assert provider.base_url == "http://box:11434"
    assert provider.model == "qwen3"
