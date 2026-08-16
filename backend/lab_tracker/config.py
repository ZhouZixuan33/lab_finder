"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated runtime settings.

    Provider intervals have conservative one-second minimums so a malformed
    environment variable cannot accidentally disable rate limiting.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    database_path: Path = Path("data/lab_tracker.db")
    llm_base_url: AnyHttpUrl | None = None
    llm_api_key: SecretStr
    llm_model: str = Field(min_length=1)
    tavily_api_key: SecretStr
    openalex_api_key: SecretStr
    tavily_min_interval_seconds: float = Field(default=1.0, ge=1.0)
    openalex_min_interval_seconds: float = Field(default=1.0, ge=1.0)
    web_host_min_interval_seconds: float = Field(default=1.0, ge=1.0)

    @field_validator("llm_base_url", mode="before")
    @classmethod
    def normalize_blank_base_url(cls, value: Any) -> Any:
        """Treat a blank optional URL the same as an unset value."""

        if isinstance(value, str) and not value.strip():
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    """Return one validated settings object per process."""

    return Settings()  # type: ignore[call-arg]
