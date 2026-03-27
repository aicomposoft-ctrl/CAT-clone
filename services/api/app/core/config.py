"""
Application settings for CAT API.

All security-critical settings are validated at startup via validate_required_secrets().
Missing JWT_SECRET or POSTGRES_URL causes sys.exit(1) — no silent fallbacks.

Usage in main.py:
    from app.core.config import validate_required_secrets, get_settings
    validate_required_secrets()  # call before any DB connections
    settings = get_settings()
"""

import logging
import os
import sys
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """
    Application configuration loaded from environment variables.

    Required fields have no defaults and will raise ValidationError on startup
    if absent — this is intentional, 12-factor app style.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- Security-critical (no defaults) ---
    JWT_SECRET: str = Field(
        ...,  # required — no default
        min_length=32,
        description="HS256 signing secret. Minimum 32 random bytes (secrets.token_hex(32)).",
    )
    POSTGRES_URL: str = Field(
        ...,  # required — no default
        description="Full async PostgreSQL connection string (asyncpg driver).",
    )

    # --- Token TTLs ---
    ACCESS_TOKEN_EXPIRE_SECONDS: int = Field(
        default=900,  # 15 minutes
        ge=60,
        le=3600,
        description="Access token lifetime in seconds.",
    )
    REFRESH_TOKEN_EXPIRE_SECONDS: int = Field(
        default=604800,  # 7 days
        ge=3600,
        le=2592000,  # 30 days max
        description="Refresh token lifetime in seconds.",
    )

    # --- Runtime ---
    APP_ENV: str = Field(
        default="development",
        description="Runtime environment: development | staging | production.",
    )

    @field_validator("JWT_SECRET")
    @classmethod
    def jwt_secret_must_have_sufficient_entropy(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError(
                "JWT_SECRET must be at least 32 characters. "
                "Generate with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        return v

    @field_validator("APP_ENV")
    @classmethod
    def app_env_must_be_valid(cls, v: str) -> str:
        valid = {"development", "staging", "production"}
        if v not in valid:
            raise ValueError(f"APP_ENV must be one of: {valid}")
        return v


def validate_required_secrets() -> None:
    """
    Validate that JWT_SECRET and POSTGRES_URL are present in the environment.

    Calls sys.exit(1) if any are missing — service must not start without secrets.
    This is the early-exit guard before pydantic-settings loads the full config.

    Call this in FastAPI lifespan BEFORE any DB connections.
    """
    required = ["JWT_SECRET", "POSTGRES_URL"]
    missing = [s for s in required if not os.environ.get(s)]
    if missing:
        logger.critical(
            "Missing required secrets: %s. "
            "Set them in environment or .env file before starting.",
            missing,
        )
        sys.exit(1)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return cached Settings instance.

    The cache ensures Settings() is constructed once per process.
    Call validate_required_secrets() before the first call to this function.
    """
    return Settings()
