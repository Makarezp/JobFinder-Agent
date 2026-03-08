from typing import cast

from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from app.core.config import settings

GEMINI = "gemini-flash-latest"
DEEPSEEK = "deepseek-chat"


def get_active_model(temperature: float = 0) -> BaseChatModel:
    """Factory that returns the configured LLM based on ACTIVE_LLM_MODEL setting."""
    if settings.ACTIVE_LLM_MODEL == DEEPSEEK:
        return cast(
            BaseChatModel,
            ChatOpenAI(
                model=DEEPSEEK,
                api_key=settings.DEEPSEEK_API_KEY,  # type: ignore[arg-type]
                base_url="https://api.deepseek.com",
                temperature=temperature,
            ),
        )

    if settings.ACTIVE_LLM_MODEL == GEMINI:
        if not settings.GEMINI_API_KEY:
            raise OSError(f"GEMINI_API_KEY is required when ACTIVE_LLM_MODEL={GEMINI!r}. Set it in your .env file.")
        return cast(
            BaseChatModel,
            ChatGoogleGenerativeAI(
                model=GEMINI,
                google_api_key=settings.GEMINI_API_KEY,
                temperature=temperature,
            ),
        )

    raise ValueError(f"Unsupported ACTIVE_LLM_MODEL: {settings.ACTIVE_LLM_MODEL!r}. Supported: {GEMINI!r}, {DEEPSEEK!r}")
