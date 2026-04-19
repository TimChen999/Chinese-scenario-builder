"""Settings loader backed by pydantic-settings.

Values come from process environment plus an optional `.env` file in
the backend directory. Never log the resolved settings -- they hold
secrets (Gemini). See DESIGN.md Section 12.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly typed application configuration.

    Construct via :func:`get_settings`; tests can call
    ``get_settings.cache_clear()`` and re-call with overridden env vars
    to swap configuration between cases.

    Field defaults are chosen to keep local dev frictionless: SQLite
    in `./data/`, image cache alongside it, CORS allowing only the
    Vite dev origin. The Gemini API key defaults to empty string so
    the app can boot without it, but ``_gemini.get_client`` raises
    loudly if a downstream stage tries to use an unset key.

    Image search uses the keyless DuckDuckGo backend (see
    ``app/agent/search.py``) so no second credential is required.
    """

    GEMINI_API_KEY: str = Field(default="", description="Google Gemini API key")

    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./data/scenarios.db",
        description="SQLAlchemy async URL",
    )
    IMAGE_STORAGE_DIR: str = Field(
        default="./data/images",
        description="On-disk folder for cached source images",
    )
    ALLOWED_ORIGINS: str = Field(
        default="http://localhost:5173",
        description="Comma-separated list of CORS origins",
    )
    LOG_LEVEL: str = Field(default="INFO")

    # Test gate. Live tests cost money + require network; off by default.
    RUN_LIVE_TESTS: str = Field(default="")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def allowed_origins_list(self) -> list[str]:
        """Parse :attr:`ALLOWED_ORIGINS` into a list for FastAPI's CORS."""
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def image_storage_path(self) -> Path:
        """Return :attr:`IMAGE_STORAGE_DIR` as a :class:`Path`."""
        return Path(self.IMAGE_STORAGE_DIR)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Cached so every request does not re-parse the environment. Tests
    that need to mutate config should call ``get_settings.cache_clear()``
    after monkey-patching env vars.
    """
    return Settings()
