import os
import tempfile
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    APP_NAME: str = "CVviewer"
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = True

    # LLM
    GEMINI_API_KEY: str
    GEMINI_MODEL_NAME: str = "gemini-flash-latest"

    # LangSmith
    LANGCHAIN_TRACING_V2: bool = False
    LANGCHAIN_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGCHAIN_API_KEY: str | None = None
    LANGCHAIN_PROJECT: str = "default"

    # JSearch (RapidAPI)
    JSEARCH_API_KEY: str | None = None

    # Database
    DATABASE_URL: str | None = None
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "cvviewer"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    # Data
    DATA_DIR: Path = Path("data")

    @property
    def USER_MEMORY_DB_PATH(self) -> Path:
        return self.DATA_DIR / "user_memory.db"

    @property
    def STATE_LOG_PATH(self) -> Path:
        return Path(tempfile.gettempdir()) / "cvviewer_state_debug.log"

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)


settings = Settings()

# LangSmith reads directly from os.environ at import time, not from pydantic settings.
# Propagate the values here so the SDK picks them up regardless of how the app is started.
if settings.LANGCHAIN_TRACING_V2:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_ENDPOINT"] = settings.LANGCHAIN_ENDPOINT
    os.environ["LANGCHAIN_PROJECT"] = settings.LANGCHAIN_PROJECT
    if settings.LANGCHAIN_API_KEY:
        os.environ["LANGCHAIN_API_KEY"] = settings.LANGCHAIN_API_KEY
