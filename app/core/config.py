from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    APP_NAME: str = "AI Scraper Bot"
    APP_ENV: str = "development"
    DEBUG: bool = True

    # LLM
    GEMINI_API_KEY: str

    # LangSmith
    LANGCHAIN_TRACING_V2: bool = False
    LANGCHAIN_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGCHAIN_API_KEY: Optional[str] = None
    LANGCHAIN_PROJECT: str = "default"

    # Adzuna
    ADZUNA_APP_ID: Optional[str] = None
    ADZUNA_APP_KEY: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)


settings = Settings()
