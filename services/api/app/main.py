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

from app.core.config import get_settings, validate_required_secrets
from app.auth.router import router as auth_router
from app.catalog.router import brand_router, platform_router, sku_platform_router, sku_router
from app.catalog.reference_router import reference_router
from app.stock.router import router as stock_router

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


_settings = get_settings()
_is_production = _settings.APP_ENV == "production"

app = FastAPI(
    title="CAT API",
    description="Commerce Analytics Tool — SaaS monitoring platform for FMCG brands",
    version="1.0.0",
    lifespan=lifespan,
    # Swagger UI and ReDoc are disabled in production to avoid leaking API surface.
    # In development/staging they are available at /docs and /redoc.
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
)

app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(brand_router, prefix="/api/v1/brands", tags=["brands"])
app.include_router(sku_router, prefix="/api/v1/skus", tags=["skus"])
app.include_router(platform_router, prefix="/api/v1/platforms", tags=["platforms"])
app.include_router(sku_platform_router, prefix="/api/v1/sku-platforms", tags=["sku-platforms"])
app.include_router(reference_router, prefix="/api/v1/skus", tags=["reference"])
app.include_router(stock_router, prefix="/api/v1/stock", tags=["stock"])
