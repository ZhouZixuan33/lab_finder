from pathlib import Path

import pytest
from pydantic import ValidationError

from lab_tracker.config import Settings


def valid_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_path": Path("data/test.db"),
        "llm_api_key": "llm-secret",
        "llm_model": "test-model",
        "tavily_api_key": "tavily-secret",
        "openalex_api_key": "openalex-secret",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_defaults_to_safe_provider_intervals() -> None:
    settings = valid_settings()

    assert settings.tavily_min_interval_seconds == 1.0
    assert settings.openalex_min_interval_seconds == 1.0
    assert settings.web_host_min_interval_seconds == 1.0


@pytest.mark.parametrize(
    "field",
    [
        "tavily_min_interval_seconds",
        "openalex_min_interval_seconds",
        "web_host_min_interval_seconds",
    ],
)
def test_rejects_intervals_below_one_second(field: str) -> None:
    with pytest.raises(ValidationError):
        valid_settings(**{field: 0.99})


def test_secret_values_are_redacted() -> None:
    settings = valid_settings()

    representation = repr(settings)

    assert "llm-secret" not in representation
    assert "tavily-secret" not in representation
    assert "openalex-secret" not in representation
    assert settings.llm_api_key.get_secret_value() == "llm-secret"


def test_blank_optional_base_url_becomes_none() -> None:
    settings = valid_settings(llm_base_url="")

    assert settings.llm_base_url is None
