"""
Alembic migration: 0018_add_pyaterochka_magnit_platforms

Adds Пятёрочка and Магнит to the platforms table.
These are simple traditional retailers without aggressive anti-bot protection —
L1 httpx is expected to work without Playwright warm-up.

schedule_cron offset from existing platforms:
  WB        02:00 UTC
  Ozon      03:00 UTC
  Самокат   04:00 UTC
  Lenta     05:00 UTC
  Пятёрочка 06:00 UTC  ← new
  Магнит    07:00 UTC  ← new
"""

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO platforms (id, name, type, schedule_cron, is_active)
        VALUES
            (gen_random_uuid(), 'Пятёрочка', 'retailer', '0 6 * * *', TRUE),
            (gen_random_uuid(), 'Магнит',    'retailer', '0 7 * * *', TRUE)
        ON CONFLICT (name) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM platforms WHERE name IN ('Пятёрочка', 'Магнит')
        """
    )
