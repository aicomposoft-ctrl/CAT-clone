"""
CAT API — FastAPI application entry point.

Startup sequence:
  1. validate_required_secrets() — exits with code 1 if JWT_SECRET or
     POSTGRES_URL are missing. This prevents the service from starting
     in a broken state.
  2. FastAPI app initialises routers and middleware.

Never add fallback defaults for security-critical secrets here.
See: .claude/rules/secrets-management.md
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from app.core.config import validate_required_secrets
from app.auth.router import router as auth_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan handler.

    Runs validate_required_secrets() before accepting traffic so that
    a misconfigured deployment fails fast and noisily rather than serving
    broken responses.
    """
    validate_required_secrets()
    logger.info("CAT API starting up")
    yield
    logger.info("CAT API shutting down")


app = FastAPI(
    title="CAT API",
    description="Commerce Analytics Tool — SaaS monitoring platform for FMCG brands",
    version="1.0.0",
    lifespan=lifespan,
    # Disable the default /docs redirect so Nginx controls exposure
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
