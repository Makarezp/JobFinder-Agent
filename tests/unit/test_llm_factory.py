"""Unit tests for the LLM factory (app.core.llm)."""

import pytest
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

import app.core.llm as llm_module
from app.core.llm import DEEPSEEK, GEMINI, get_active_model


def test_get_active_model_returns_google_genai(monkeypatch: pytest.MonkeyPatch) -> None:
    """When ACTIVE_LLM_MODEL is GEMINI, factory returns ChatGoogleGenerativeAI."""
    monkeypatch.setattr(llm_module.settings, "ACTIVE_LLM_MODEL", GEMINI)
    monkeypatch.setattr(llm_module.settings, "GEMINI_API_KEY", "fake-google-key")

    model = get_active_model(temperature=0)

    assert isinstance(model, ChatGoogleGenerativeAI)


def test_get_active_model_returns_deepseek(monkeypatch: pytest.MonkeyPatch) -> None:
    """When ACTIVE_LLM_MODEL is DEEPSEEK, factory returns ChatOpenAI with DeepSeek base_url."""
    monkeypatch.setattr(llm_module.settings, "ACTIVE_LLM_MODEL", DEEPSEEK)
    monkeypatch.setattr(llm_module.settings, "DEEPSEEK_API_KEY", "fake-deepseek-key")

    model = get_active_model(temperature=0)

    assert isinstance(model, ChatOpenAI)
    assert str(model.openai_api_base) == "https://api.deepseek.com"


def test_get_active_model_raises_without_gemini_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Factory raises OSError when Gemini is selected but GEMINI_API_KEY is missing."""
    monkeypatch.setattr(llm_module.settings, "ACTIVE_LLM_MODEL", GEMINI)
    monkeypatch.setattr(llm_module.settings, "GEMINI_API_KEY", None)

    with pytest.raises(OSError, match="GEMINI_API_KEY is required"):
        get_active_model()


def test_get_active_model_raises_on_unknown_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Factory raises ValueError for any unrecognised ACTIVE_LLM_MODEL value."""
    monkeypatch.setattr(llm_module.settings, "ACTIVE_LLM_MODEL", "anthropic/claude")

    with pytest.raises(ValueError, match="Unsupported ACTIVE_LLM_MODEL"):
        get_active_model()
