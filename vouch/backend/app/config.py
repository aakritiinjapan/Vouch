"""Environment settings. MOCK_MODE lets the whole app run offline against fixtures."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mock_mode: bool = True                       # run without Bright Data / Anthropic
    database_url: str = "sqlite:///vouch.db"

    brightdata_api_token: str = ""               # required only when mock_mode is false
    anthropic_api_key: str = ""                  # required only for the LLM judge (Phase 3)
    llm_judge_model: str = "claude-sonnet-4-6"


settings = Settings()
