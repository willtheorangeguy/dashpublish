"""Tests for dashpublish.config."""

from __future__ import annotations

from pathlib import Path

import pytest

from dashpublish import config as config_mod


@pytest.fixture(autouse=True)
def _reset_config_env(monkeypatch):
    for var in (
        "DASHPUBLISH_CONFIG",
        "GEMINI_API_KEY",
        "DASHSCOPE_API_KEY",
        "YOUTUBE_CLIENT_SECRETS",
        "DASHPUBLISH_FAKE",
    ):
        monkeypatch.delenv(var, raising=False)
    config_mod.reset_config()
    yield
    config_mod.reset_config()


def test_defaults_when_no_toml(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHPUBLISH_CONFIG", str(tmp_path / "missing.toml"))
    cfg = config_mod.load_config()
    assert cfg.general.data_dir == "~/.dashpublish"
    assert cfg.embeddings.backend == "gemini"
    assert cfg.llm.provider == "gemini"
    assert cfg.llm.model == "gemini-2.5-flash"
    assert cfg.scan.default_threshold == 0.5
    assert cfg.compile.short_max_s == 60
    assert cfg.youtube.default_privacy == "private"
    assert cfg.youtube.category_id == "2"
    assert cfg.config_path is None
    assert cfg.fake_mode is False


def test_toml_load(monkeypatch, tmp_path):
    toml_path = tmp_path / "dashpublish.toml"
    toml_path.write_text(
        """
[general]
footage_dir = "/data/footage"
data_dir = "/data/dash"

[embeddings]
backend = "dashscope"

[llm]
provider = "ollama"
model = "custom-model"

[scan]
default_threshold = 0.7
save_top = 5

[youtube]
default_privacy = "unlisted"
""".strip()
    )
    monkeypatch.setenv("DASHPUBLISH_CONFIG", str(toml_path))
    cfg = config_mod.load_config()
    assert cfg.general.footage_dir == "/data/footage"
    assert cfg.general.data_dir == "/data/dash"
    assert cfg.embeddings.backend == "dashscope"
    assert cfg.llm.provider == "ollama"
    assert cfg.llm.model == "custom-model"
    assert cfg.scan.default_threshold == 0.7
    assert cfg.scan.save_top == 5
    assert cfg.youtube.default_privacy == "unlisted"
    assert cfg.config_path == str(toml_path)


def test_env_secret_overlay(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHPUBLISH_CONFIG", str(tmp_path / "missing.toml"))
    monkeypatch.setenv("GEMINI_API_KEY", "gem-123")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dash-456")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRETS", "/secrets/client.json")
    cfg = config_mod.load_config()
    assert cfg.gemini_api_key == "gem-123"
    assert cfg.dashscope_api_key == "dash-456"
    assert cfg.youtube_client_secrets == "/secrets/client.json"


def test_fake_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHPUBLISH_CONFIG", str(tmp_path / "missing.toml"))
    monkeypatch.setenv("DASHPUBLISH_FAKE", "1")
    cfg = config_mod.load_config()
    assert cfg.fake_mode is True


def test_load_config_is_cached(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHPUBLISH_CONFIG", str(tmp_path / "missing.toml"))
    first = config_mod.load_config()
    second = config_mod.load_config()
    assert first is second
    config_mod.reset_config()
    third = config_mod.load_config()
    assert third is not first


def test_example_toml_matches_schema():
    """The shipped example config must load cleanly into the schema."""
    example = Path(__file__).resolve().parents[2] / "dashpublish.example.toml"
    import tomllib

    data = tomllib.loads(example.read_text())
    cfg = config_mod.Config(
        general=config_mod.GeneralConfig(**data["general"]),
        embeddings=config_mod.EmbeddingsConfig(**data["embeddings"]),
        llm=config_mod.LLMConfig(**data["llm"]),
        scan=config_mod.ScanConfig(**data["scan"]),
        compile=config_mod.CompileConfig(**data["compile"]),
        youtube=config_mod.YouTubeConfig(**data["youtube"]),
    )
    assert cfg.embeddings.backend == "gemini"
