"""Unit tests for the LLM factory (app.core.llm)."""

import pytest
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

import app.core.llm as llm_module
from app.core.llm import get_active_model, get_summarisation_model


def test_get_active_model_returns_google_genai(monkeypatch: pytest.MonkeyPatch) -> None:
    """When ACTIVE_LLM_MODEL is a Gemini variant, factory returns ChatGoogleGenerativeAI."""
    monkeypatch.setattr(llm_module.settings, "ACTIVE_LLM_MODEL", "gemini-flash-latest")
    monkeypatch.setattr(llm_module.settings, "GEMINI_API_KEY", "fake-google-key")

    model = get_active_model(temperature=0)

    assert isinstance(model, ChatGoogleGenerativeAI)


def test_get_active_model_returns_deepseek(monkeypatch: pytest.MonkeyPatch) -> None:
    """When ACTIVE_LLM_MODEL is deepseek-chat, factory returns ChatOpenAI with DeepSeek base_url."""
    monkeypatch.setattr(llm_module.settings, "ACTIVE_LLM_MODEL", "deepseek-chat")
    monkeypatch.setattr(llm_module.settings, "DEEPSEEK_API_KEY", "fake-deepseek-key")

    model = get_active_model(temperature=0)

    assert isinstance(model, ChatOpenAI)
    assert str(model.openai_api_base) == "https://api.deepseek.com"


def test_get_active_model_raises_without_gemini_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Factory raises OSError when Gemini is selected but GEMINI_API_KEY is missing."""
    monkeypatch.setattr(llm_module.settings, "ACTIVE_LLM_MODEL", "gemini-flash-latest")
    monkeypatch.setattr(llm_module.settings, "GEMINI_API_KEY", None)

    with pytest.raises(OSError, match="GEMINI_API_KEY is required"):
        get_active_model()


def test_get_active_model_raises_on_unknown_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Factory raises ValueError for any unrecognised model value."""
    monkeypatch.setattr(llm_module.settings, "ACTIVE_LLM_MODEL", "anthropic/claude")

    with pytest.raises(ValueError, match="Unsupported model"):
        get_active_model()


def test_get_active_model_supports_arbitrary_gemini_variant(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any model name starting with 'gemini' is routed to ChatGoogleGenerativeAI."""
    monkeypatch.setattr(llm_module.settings, "ACTIVE_LLM_MODEL", "gemini-3.1-pro-preview")
    monkeypatch.setattr(llm_module.settings, "GEMINI_API_KEY", "fake-google-key")

    model = get_active_model(temperature=0)

    assert isinstance(model, ChatGoogleGenerativeAI)


def test_get_summarisation_model_returns_google_genai(monkeypatch: pytest.MonkeyPatch) -> None:
    """When SUMMARISATION_LLM_MODEL is a Gemini variant, factory returns ChatGoogleGenerativeAI."""
    monkeypatch.setattr(llm_module.settings, "SUMMARISATION_LLM_MODEL", "gemini-flash-latest")
    monkeypatch.setattr(llm_module.settings, "GEMINI_API_KEY", "fake-google-key")

    model = get_summarisation_model(temperature=0)

    assert isinstance(model, ChatGoogleGenerativeAI)


def test_get_summarisation_model_returns_deepseek(monkeypatch: pytest.MonkeyPatch) -> None:
    """When SUMMARISATION_LLM_MODEL is deepseek-chat, factory returns ChatOpenAI."""
    monkeypatch.setattr(llm_module.settings, "SUMMARISATION_LLM_MODEL", "deepseek-chat")
    monkeypatch.setattr(llm_module.settings, "DEEPSEEK_API_KEY", "fake-deepseek-key")

    model = get_summarisation_model(temperature=0)

    assert isinstance(model, ChatOpenAI)
    assert str(model.openai_api_base) == "https://api.deepseek.com"


def test_get_summarisation_model_raises_on_unknown_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Summarisation factory raises ValueError for unrecognised model."""
    monkeypatch.setattr(llm_module.settings, "SUMMARISATION_LLM_MODEL", "unknown/model")

    with pytest.raises(ValueError, match="Unsupported model"):
        get_summarisation_model()
