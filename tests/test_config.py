import pytest

from atrium.config import ConfigError, Settings, apply_env


def test_defaults():
    s = Settings()
    assert s.chat_model.startswith("gpt-")
    assert s.retrieval_k > 0
    assert s.chroma_dir.name == "chroma_db"


def test_missing_secret_raises(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ConfigError):
        _ = Settings().openai_api_key


def test_apply_env_lowercases_tracing_flag(monkeypatch):
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    apply_env({"LANGSMITH_TRACING": True, "SOME_KEY": "Value", "nested": {"x": 1}})
    import os

    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["SOME_KEY"] == "Value"  # non-flag values kept verbatim
    assert "nested" not in os.environ
