"""
Alembic migration: 0015_platform_scraper_mode_defaults

Sets platform-level scraper_mode defaults based on platform capabilities:

  Wildberries  → 'auto'        (card.wb.ru public API works well)
  Ozon         → 'auto'        (composer-api.bx works well)
  Lenta        → 'playwright'  (site behind QRATOR, mobile API unverified;
                                skip L1 httpx, go straight to Playwright L2)
  Самокат      → 'playwright'  (full SPA, geo-gated; L1 unverified; use L2)

Future FMCG platforms (Magnit, X5, Auchan, Metro) should be inserted with
scraper_mode='playwright' or 'agent' — no public APIs exist for these.
See docs/features/adaptive-scraper-pipeline/ for rationale.

Pattern for adding a new platform via SQL seed:
    INSERT INTO platforms (id, name, is_active, scraper_mode)
    VALUES (gen_random_uuid(), 'Магнит', true, 'playwright')
    ON CONFLICT DO NOTHING;

Usage:
    alembic upgrade head       # applies upgrade()
    alembic downgrade -1       # applies downgrade()
"""

from alembic import op

# Alembic revision identifiers
revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

# Platforms known to require Playwright from the start (L1 httpx unreliable).
# Values must match Platform.name in DB exactly (case-sensitive).
_PLAYWRIGHT_PLATFORMS = ("Lenta", "Самокат")

# Platforms where auto-detection works well (default, but set explicitly for clarity).
_AUTO_PLATFORMS = ("Wildberries", "Ozon")


def upgrade() -> None:
    # Mark platforms where L1 httpx is known to fail as playwright-first.
    # NULL-safe: only updates rows that exist; no error if a platform is missing.
    op.execute(
        f"""
        UPDATE platforms
           SET scraper_mode = 'playwright'
         WHERE name IN ({_sql_list(_PLAYWRIGHT_PLATFORMS)})
        """
    )
    # Explicitly set auto for core API platforms (idempotent — server default is 'auto').
    op.execute(
        f"""
        UPDATE platforms
           SET scraper_mode = 'auto'
         WHERE name IN ({_sql_list(_AUTO_PLATFORMS)})
        """
    )


def downgrade() -> None:
    # Reset all touched platforms back to 'auto' (server default).
    all_names = _PLAYWRIGHT_PLATFORMS + _AUTO_PLATFORMS
    op.execute(
        f"""
        UPDATE platforms
           SET scraper_mode = 'auto'
         WHERE name IN ({_sql_list(all_names)})
        """
    )


def _sql_list(names: tuple[str, ...]) -> str:
    """Return a SQL-safe quoted list: 'Lenta', 'Самокат'"""
    return ", ".join(f"'{n}'" for n in names)
