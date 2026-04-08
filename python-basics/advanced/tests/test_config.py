"""Unit tests for app.config."""

import os

import pytest


def test_openrouter_url_constant():
    """OPENROUTER_URL is the OpenRouter chat completions endpoint."""
    from app.config import OPENROUTER_URL

    assert OPENROUTER_URL == "https://openrouter.ai/api/v1/chat/completions"


def test_default_model_constant():
    """DEFAULT_MODEL is set to a free model identifier."""
    from app.config import DEFAULT_MODEL

    assert DEFAULT_MODEL == "google/gemma-3-27b-it:free"


def test_openrouter_api_key_default_when_unset(monkeypatch):
    """OPENROUTER_API_KEY is empty string when env var is not set."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    # Re-import to pick up env change (module may already be cached)
    import importlib
    import app.config as config
    importlib.reload(config)
    assert config.OPENROUTER_API_KEY == ""


def test_openrouter_api_key_from_env(monkeypatch):
    """OPENROUTER_API_KEY reads from OPENROUTER_API_KEY env var."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-key-123")
    import importlib
    import app.config as config
    importlib.reload(config)
    assert config.OPENROUTER_API_KEY == "sk-test-key-123"
