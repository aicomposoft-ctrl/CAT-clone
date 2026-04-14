# Snippet: Startup Secrets Validation
# Category: Snippet | Language: Python
# Maturity: 🔴 Alpha | Extracted: 2026-03-27 from CAT project
#
# When to Use:
#   Any 12-factor app that must fail loudly if required env vars are missing.
#   Call this at application startup BEFORE any DB connections or service init.
#
# When NOT to Use:
#   - Non-security config with safe defaults (timeouts, feature flags, limits)
#   - Test environments where secrets are intentionally absent (use .env.test)
#
# Prerequisites:
#   Python stdlib only (os, sys, logging)
#
# Dependencies: None

import os
import sys
import logging

logger = logging.getLogger(__name__)


def validate_required_secrets(secrets: list[str]) -> None:
    """
    Validate that all required environment variables are present.
    Exits with code 1 if any are missing — no fallback defaults.

    Args:
        secrets: List of required environment variable names.

    Usage:
        REQUIRED_SECRETS = [
            "JWT_SECRET",
            "DATABASE_URL",
            "S3_ACCESS_KEY",
            "S3_SECRET_KEY",
            "SMTP_PASSWORD",
        ]
        validate_required_secrets(REQUIRED_SECRETS)  # call in main.py startup
    """
    missing = [s for s in secrets if not os.environ.get(s)]
    if missing:
        logger.critical(
            "Missing required secrets: %s. "
            "Set them in environment or .env file before starting.",
            missing,
        )
        sys.exit(1)


# --- Variant: Pydantic Settings (preferred for typed config) ---
#
# from pydantic_settings import BaseSettings
# from pydantic import Field
#
# class Settings(BaseSettings):
#     jwt_secret: str = Field(..., env="JWT_SECRET")       # ... = required, no default
#     database_url: str = Field(..., env="DATABASE_URL")
#     s3_access_key: str = Field(..., env="S3_ACCESS_KEY")
#
#     class Config:
#         env_file = ".env"
#
# settings = Settings()  # raises ValidationError on startup if missing
