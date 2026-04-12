"""
Alembic migration: 0014_adaptive_scraper_platform_fields

Extends the platform / scraping model to support adaptive, per-org credential
management without polluting the global `platforms` table (which is shared
across all tenants and must remain token-free for multi-tenant isolation).

Changes:
  1. platforms.scraper_mode VARCHAR(20) NOT NULL DEFAULT 'auto'
       Signals which collection strategy the scraper should attempt first:
       'auto'   — try token auth, fall back to Playwright, then Scrapy
       'token'  — token-only; raise if token absent
       'browser'— Playwright-only; skip token path
       'scrape' — Scrapy-only; skip browser path

  2. org_platform_credentials (new table)
       Per-org, per-platform credential + scraper config overrides.
       Keeps api_token_encrypted out of the global platforms table so that
       a cross-tenant JOIN on platforms never exposes another org's secrets.
       Columns:
         id                 UUID PK
         org_id             UUID FK → organizations(id) CASCADE DELETE
         platform_id        UUID FK → platforms(id) CASCADE DELETE
         api_token_encrypted TEXT nullable — AES-256-GCM ciphertext (key from env)
         api_token_type     VARCHAR(20) nullable — e.g. 'bearer', 'apikey', 'cookie'
         fallback_chain     JSONB nullable — ordered list of scraper modes to attempt,
                            e.g. ["token","browser","scrape"]
         selectors          JSONB nullable — CSS/XPath overrides for this platform
         created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
         updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
         UNIQUE(org_id, platform_id) — one credential record per org-platform pair

  3. idx_org_platform_credentials_org_id — hot-path index for per-org credential lookup

  4. content_scores.scraper_level SMALLINT nullable
       Records which collection tier produced the row:
         0 = token/API  1 = browser (Playwright)  2 = scrape (Scrapy)
       NULL = legacy rows or unknown.

  5. price_snapshots.scraper_level SMALLINT nullable
       Same semantics as content_scores.scraper_level.

Security note:
  api_token_encrypted stores ciphertext only. The encryption key lives in
  the ORG_TOKEN_ENCRYPTION_KEY environment variable and is NEVER stored in
  the database. See .claude/rules/secrets-management.md.

Usage:
    alembic upgrade head       # applies upgrade()
    alembic downgrade -1       # applies downgrade()
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# Alembic revision identifiers
revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Add scraper_mode to the global platforms table.
    #    NOT NULL with a server-side default so existing rows are patched
    #    atomically without a separate UPDATE statement.
    # ------------------------------------------------------------------
    op.add_column(
        "platforms",
        sa.Column(
            "scraper_mode",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'auto'"),
        ),
    )

    # ------------------------------------------------------------------
    # 2. Create org_platform_credentials — per-org, per-platform config.
    #    Deliberately separate from platforms to preserve multi-tenant
    #    isolation: the platforms table remains token-free and is safe to
    #    JOIN across the whole dataset.
    # ------------------------------------------------------------------
    op.create_table(
        "org_platform_credentials",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "platform_id",
            UUID(as_uuid=True),
            sa.ForeignKey("platforms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Ciphertext of the API token (AES-256-GCM). Key is in env var only.
        sa.Column("api_token_encrypted", sa.Text(), nullable=True),
        # Describes how the token should be transmitted: 'bearer', 'apikey', 'cookie', etc.
        sa.Column("api_token_type", sa.String(20), nullable=True),
        # Ordered fallback strategy, e.g. ["token", "browser", "scrape"].
        # NULL means: use platform-level scraper_mode with built-in defaults.
        sa.Column("fallback_chain", JSONB(), nullable=True),
        # Platform-specific CSS/XPath selector overrides for this org's scraper.
        sa.Column("selectors", JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        # Enforce exactly one credential record per org-platform combination.
        sa.UniqueConstraint("org_id", "platform_id", name="uq_org_platform_credentials"),
    )

    # ------------------------------------------------------------------
    # 3. Index: list / lookup all credential records for an org.
    #    Used on every scrape-dispatch cycle (hot path).
    # ------------------------------------------------------------------
    op.create_index(
        "idx_org_platform_credentials_org_id",
        "org_platform_credentials",
        ["org_id"],
    )

    # ------------------------------------------------------------------
    # 4. content_scores.scraper_level — records collection tier provenance.
    #    0 = token/API  |  1 = Playwright browser  |  2 = Scrapy
    #    NULL = pre-migration rows or collection method unknown.
    # ------------------------------------------------------------------
    op.add_column(
        "content_scores",
        sa.Column("scraper_level", sa.SmallInteger(), nullable=True),
    )

    # ------------------------------------------------------------------
    # 5. price_snapshots.scraper_level — same semantics as above.
    # ------------------------------------------------------------------
    op.add_column(
        "price_snapshots",
        sa.Column("scraper_level", sa.SmallInteger(), nullable=True),
    )


def downgrade() -> None:
    # Reverse in strict reverse-application order.

    # 5. Remove scraper_level from price_snapshots
    op.drop_column("price_snapshots", "scraper_level")

    # 4. Remove scraper_level from content_scores
    op.drop_column("content_scores", "scraper_level")

    # 3 + 2. Drop index then table (index must go first)
    op.drop_index(
        "idx_org_platform_credentials_org_id",
        table_name="org_platform_credentials",
    )
    op.drop_table("org_platform_credentials")

    # 1. Remove scraper_mode from platforms
    op.drop_column("platforms", "scraper_mode")
