from typing import cast

from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from app.core.config import settings


def _build_model(model_name: str, temperature: float) -> BaseChatModel:
    """Resolve a model name to a LangChain chat model instance."""
    if model_name == "deepseek-chat":
        return cast(
            BaseChatModel,
            ChatOpenAI(
                model="deepseek-chat",
                api_key=settings.DEEPSEEK_API_KEY,  # type: ignore[arg-type]
                base_url="https://api.deepseek.com",
                temperature=temperature,
            ),
        )

    if model_name.startswith("gemini"):
        if not settings.GEMINI_API_KEY:
            raise OSError(f"GEMINI_API_KEY is required when model={model_name!r}. Set it in your .env file.")
        return cast(
            BaseChatModel,
            ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=settings.GEMINI_API_KEY,
                temperature=temperature,
            ),
        )

    raise ValueError(f"Unsupported model: {model_name!r}. Supported: Gemini (gemini-*), 'deepseek-chat'")


def get_active_model(temperature: float = 0) -> BaseChatModel:
    """Factory that returns the main agent LLM based on ACTIVE_LLM_MODEL setting."""
    return _build_model(settings.ACTIVE_LLM_MODEL, temperature)


def get_summarisation_model(temperature: float = 0) -> BaseChatModel:
    """Factory that returns the summarisation LLM based on SUMMARISATION_LLM_MODEL setting."""
    return _build_model(settings.SUMMARISATION_LLM_MODEL, temperature)
