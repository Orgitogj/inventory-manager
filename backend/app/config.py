from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    app_env: Literal["development", "testing", "production"] = "development"
    database_url: str | None = None
    test_database_url: str | None = None
    session_lifetime_hours: int = Field(default=8, ge=1, le=24 * 30)

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
