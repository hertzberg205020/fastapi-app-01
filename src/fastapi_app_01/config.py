"""Centralised application settings.

This is where the program declares its dependency on the environment. Each field
below is a config value the app *requires* to run. pydantic-settings reads them
(in priority order) from real environment variables first, then from the `.env`
file, and validates them when `Settings()` is constructed at startup.

Because `database_url` / `redis_url` have no default, a missing value makes the
app fail fast at startup with a clear ValidationError — instead of crashing
later on the first database query.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchor the .env path to the project root (this file is at src/fastapi_app_01/),
# so it's found regardless of the working directory the app is launched from
# (e.g. PyCharm's green-run vs `uv run` from the repo root).
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Required — no default, so the app won't start without them.
    database_url: str
    redis_url: str


# Constructed once at import time; reused everywhere via `from ... import settings`.
settings = Settings()
