"""
Alembic migration: 0016_platform_config_and_geo_init

Adds platform_config JSONB to platforms table for per-platform browser/scraper
configuration.  Used by PlaywrightScraper (L2) to handle geo-gated platforms.

Changes:
  1. platforms.platform_config JSONB NULL
       Stores platform-specific scraper hints:
         geolocation:      {"latitude": float, "longitude": float, "accuracy": float}
                           Passed to Playwright context.new_context(geolocation=...)
                           Required for platforms that gate content by delivery address.
         geo_init_url:     URL to navigate to BEFORE the product URL.
                           Establishes delivery zone / store session.
                           Example: "https://samokat.ru"
         geo_init_wait_ms: ms to wait after geo_init_url for JS to resolve address.
                           Default 2500 if not set.

  2. Platform seed updates:
       Самокат → scraper_mode='playwright',
                 platform_config = {
                   "geolocation": {"latitude": 55.7558, "longitude": 37.6173},
                   "geo_init_url": "https://samokat.ru",
                   "geo_init_wait_ms": 2500
                 }
       Lenta   → scraper_mode='auto'   (revert from 0015 — L1 should be tried first;
                 QRATOR may allow the mobile UA; L2 Playwright is the fallback)

Rationale for Samokat geo-init:
  Samokat is a geo-gated SPA — product availability and pricing depend on the
  delivery zone (dark store selection).  Without navigating to the homepage first
  with a valid geolocation, the product page either redirects to address selection
  or returns empty/no-stock data.  Moscow centre coordinates (Tverskaya) are used
  as the default; this selects the nearest Samokat dark store.

Usage:
    alembic upgrade head
    alembic downgrade -1
"""

import json
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

# Moscow centre — Tverskaya street coordinates
_MOSCOW_GEO = {
    "latitude": 55.7558,
    "longitude": 37.6173,
    "accuracy": 10,
}

_SAMOCAT_CONFIG = {
    "geolocation": _MOSCOW_GEO,
    "geo_init_url": "https://samokat.ru",
    "geo_init_wait_ms": 2500,
}


def upgrade() -> None:
    # 1. Add platform_config column
    op.add_column(
        "platforms",
        sa.Column("platform_config", JSONB(), nullable=True),
    )

    # 2. Configure Самокат — geo-gated, needs delivery address init via Playwright
    op.execute(
        f"""
        UPDATE platforms
           SET scraper_mode    = 'playwright',
               platform_config = '{json.dumps(_SAMOCAT_CONFIG)}'::jsonb
         WHERE name = 'Самокат'
        """
    )

    # 3. Revert Lenta to 'auto' — L1 httpx should be tried first (QRATOR may pass
    #    the mobile User-Agent); Playwright L2 is the automatic fallback on failure.
    op.execute(
        """
        UPDATE platforms
           SET scraper_mode    = 'auto',
               platform_config = NULL
         WHERE name = 'Lenta'
        """
    )


def downgrade() -> None:
    # Restore previous scraper_mode values (from migration 0015)
    op.execute(
        """
        UPDATE platforms
           SET scraper_mode    = 'playwright',
               platform_config = NULL
         WHERE name = 'Самокат'
        """
    )
    op.execute(
        """
        UPDATE platforms
           SET scraper_mode    = 'playwright',
               platform_config = NULL
         WHERE name = 'Lenta'
        """
    )
    op.drop_column("platforms", "platform_config")
