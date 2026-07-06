"""Configuration for dashpublish.

Non-secret settings are loaded from a TOML file (path from the ``DASHPUBLISH_CONFIG``
environment variable, defaulting to ``./dashpublish.toml``). If the file is missing,
built-in defaults are used. Secrets are read *only* from environment variables and are
never stored in the TOML file.

Use :func:`load_config` to get a cached :class:`Config`. Call :func:`reset_config` in
tests to clear the cache.
"""

from __future__ import annotations

import logging
import os
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

EmbeddingBackend = Literal["gemini", "dashscope", "local"]
LLMProviderName = Literal["gemini", "ollama"]
TransitionName = Literal["cut", "crossfade"]
PrivacyStatus = Literal["private", "unlisted"]

DEFAULT_CONFIG_PATH = "./dashpublish.toml"


class GeneralConfig(BaseModel):
    footage_dir: str = ""
    data_dir: str = "~/.dashpublish"


class EmbeddingsConfig(BaseModel):
    backend: EmbeddingBackend = "gemini"


class LLMConfig(BaseModel):
    provider: LLMProviderName = "gemini"
    model: str = "gemini-2.5-flash"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"


class ScanConfig(BaseModel):
    default_threshold: float = 0.5
    save_top: int = 3
    dedupe_window_s: int = 3
    rerank: bool = True


class CompileConfig(BaseModel):
    short_max_s: int = 60
    long_target_s: int = 300
    music_duck_db: int = -12
    transition: TransitionName = "cut"


class YouTubeConfig(BaseModel):
    default_privacy: PrivacyStatus = "private"
    category_id: str = "2"


class Config(BaseModel):
    """Fully-resolved dashpublish configuration."""

    general: GeneralConfig = Field(default_factory=GeneralConfig)
    embeddings: EmbeddingsConfig = Field(default_factory=EmbeddingsConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    scan: ScanConfig = Field(default_factory=ScanConfig)
    compile: CompileConfig = Field(default_factory=CompileConfig)
    youtube: YouTubeConfig = Field(default_factory=YouTubeConfig)

    # Secrets and runtime toggles — env only, never persisted to TOML.
    gemini_api_key: str | None = None
    dashscope_api_key: str | None = None
    youtube_client_secrets: str | None = None
    fake_mode: bool = False

    # Path the config was loaded from (None if defaults were used).
    config_path: str | None = None


def _read_toml(path: Path) -> dict:
    if not path.exists():
        if os.environ.get("DASHPUBLISH_CONFIG"):
            logging.getLogger(__name__).warning(
                "config file %s (from DASHPUBLISH_CONFIG) not found; using built-in defaults",
                path,
            )
        return {}
    if path.is_dir():
        raise RuntimeError(
            f"config path {path} is a directory, not a file. In Docker this usually "
            "means ./dashpublish.toml did not exist on the host when compose created "
            "the bind mount — remove the directory, create the file "
            "(cp dashpublish.example.toml dashpublish.toml), and restart."
        )
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _build_config() -> Config:
    config_path = os.environ.get("DASHPUBLISH_CONFIG", DEFAULT_CONFIG_PATH)
    path = Path(config_path).expanduser()
    data = _read_toml(path)

    config = Config(
        general=GeneralConfig(**data.get("general", {})),
        embeddings=EmbeddingsConfig(**data.get("embeddings", {})),
        llm=LLMConfig(**data.get("llm", {})),
        scan=ScanConfig(**data.get("scan", {})),
        compile=CompileConfig(**data.get("compile", {})),
        youtube=YouTubeConfig(**data.get("youtube", {})),
        gemini_api_key=os.environ.get("GEMINI_API_KEY") or None,
        dashscope_api_key=os.environ.get("DASHSCOPE_API_KEY") or None,
        youtube_client_secrets=os.environ.get("YOUTUBE_CLIENT_SECRETS") or None,
        fake_mode=_truthy(os.environ.get("DASHPUBLISH_FAKE")),
        config_path=str(path) if path.exists() else None,
    )
    return config


@lru_cache(maxsize=1)
def load_config() -> Config:
    """Return the cached, fully-resolved configuration."""
    return _build_config()


def reset_config() -> None:
    """Clear the cached configuration (for tests)."""
    load_config.cache_clear()
