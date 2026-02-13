from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    APP_NAME: str = "AI Scraper Bot"
    APP_ENV: str = "development"
    DEBUG: bool = True

    # LLM
    GEMINI_API_KEY: str
    GEMINI_MODEL_NAME: str = "gemini-flash-latest"

    # LangSmith
    LANGCHAIN_TRACING_V2: bool = False
    LANGCHAIN_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGCHAIN_API_KEY: str | None = None
    LANGCHAIN_PROJECT: str = "default"

    # Adzuna
    ADZUNA_APP_ID: str | None = None
    ADZUNA_APP_KEY: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)


settings = Settings()
