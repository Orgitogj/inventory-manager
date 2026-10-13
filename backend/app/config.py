from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    app_env: Literal["development", "testing", "production"] = "development"
    database_url: str | None = None
    test_database_url: str | None = None
    session_lifetime_hours: int = Field(default=8, ge=1, le=24 * 30)
    cors_origins: Annotated[list[str], NoDecode] = []
    login_max_attempts: int = Field(default=5, ge=1, le=100)
    login_window_minutes: int = Field(default=15, ge=1, le=24 * 60)
    login_max_attempts_per_ip: int = Field(default=30, ge=1, le=10_000)

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]

        return value

    @field_validator("cors_origins")
    @classmethod
    def reject_wildcard_origin(cls, origins: list[str]) -> list[str]:
        if any("*" in origin for origin in origins):
            raise ValueError("CORS origins must be explicit; '*' is not allowed.")

        return origins
