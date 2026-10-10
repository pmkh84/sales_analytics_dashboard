from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        extra="ignore",
        hide_input_in_errors=True,
    )
    database_url: str
    frontend_url: str = "http://localhost:5173"
    openai_api_key: str = ""
    openai_model: str = "gpt-5.6-luna"
    telegram_bot_token: SecretStr = Field(default=SecretStr(""), repr=False)
    telegram_enabled: bool = True
    telegram_api_url: str = "https://api.telegram.org"
    telegram_timeout_seconds: float = Field(default=3.0, gt=0, le=30, allow_inf_nan=False)
    exchange_rate_api_key: SecretStr = Field(default=SecretStr(""), repr=False)
    exchange_rate_api_url: str = "https://api.navasan.tech/latest/"
    exchange_rate_cache_ttl_seconds: int = Field(default=120, ge=1, le=86400)
    exchange_rate_timeout_seconds: float = Field(default=5.0, gt=0, le=30, allow_inf_nan=False)

    @field_validator("exchange_rate_api_url")
    @classmethod
    def valid_exchange_rate_api_url(cls, value: str) -> str:
        from urllib.parse import urlsplit

        url = urlsplit(value)
        if (
            url.scheme != "https"
            or not url.netloc
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
        ):
            raise ValueError("EXCHANGE_RATE_API_URL must be HTTPS without credentials, query or fragment.")
        return value

    @field_validator("telegram_api_url")
    @classmethod
    def valid_telegram_api_url(cls, value: str) -> str:
        from urllib.parse import urlsplit

        url = urlsplit(value)
        if (
            url.scheme != "https"
            or not url.netloc
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
        ):
            raise ValueError("TELEGRAM_API_URL must be an HTTPS URL without credentials, query or fragment.")
        return value.rstrip("/")

    @field_validator("database_url")
    @classmethod
    def postgres_only(cls, value: str) -> str:
        if value.startswith("postgres://"):
            value = value.replace("postgres://", "postgresql+psycopg://", 1)
        elif value.startswith("postgresql://"):
            value = value.replace("postgresql://", "postgresql+psycopg://", 1)
        if make_url(value).drivername != "postgresql+psycopg":
            raise ValueError("DATABASE_URL must be a PostgreSQL URL.")
        return value

    @field_validator("frontend_url")
    @classmethod
    def valid_origin(cls, value: str) -> str:
        from urllib.parse import urlsplit

        origin = urlsplit(value)
        if (
            origin.scheme not in {"http", "https"}
            or not origin.netloc
            or origin.path not in {"", "/"}
            or origin.query
            or origin.fragment
        ):
            raise ValueError("FRONTEND_URL must be one exact HTTP(S) origin.")
        return value.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()
