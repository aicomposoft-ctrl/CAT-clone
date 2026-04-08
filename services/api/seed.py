"""
Seed script: create all tables + default admin user.

Usage (inside api container):
    python seed.py

Creates:
    Organization: "Demo Org" (slug: demo)
    User: admin@cat.local / Admin1234! (role: admin)
"""

import asyncio
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ── DB URL ─────────────────────────────────────────────────────────────────────
POSTGRES_URL = os.environ.get(
    "POSTGRES_URL",
    "postgresql+asyncpg://cat_user:cat_password@localhost:5432/cat_db",
)

engine = create_async_engine(POSTGRES_URL, echo=False)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def create_tables() -> None:
    """Create all tables from ORM metadata."""
    # Import all model modules so they register against Base
    from app.core.database import Base  # noqa: F401
    import app.auth.models  # noqa: F401
    import app.catalog.models  # noqa: F401
    import app.alerts.models  # noqa: F401
    import app.api_keys.models  # noqa: F401  (might not exist yet)
    import app.clients.models  # noqa: F401
    import app.content.models  # noqa: F401
    import app.prices.models  # noqa: F401
    # app.reports.models intentionally skipped — read-only aliases of other tables
    import app.reviews.models  # noqa: F401
    import app.stock.models  # noqa: F401
    import app.stock.stock_history_model  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Tables created (or already exist)")


async def seed_platforms() -> None:
    """Insert default platforms if not present."""
    # Only platforms with implemented scrapers (collector/app/scrapers/)
    platforms = [
        {"name": "Wildberries", "type": "marketplace", "schedule_cron": "0 2 * * *"},
        {"name": "Ozon", "type": "marketplace", "schedule_cron": "0 3 * * *"},
        {"name": "Самокат", "type": "darkstore", "schedule_cron": "0 4 * * *"},
        {"name": "Лента", "type": "retailer", "schedule_cron": "0 5 * * *"},
    ]
    async with SessionLocal() as db:
        result = await db.execute(text("SELECT COUNT(*) FROM platforms"))
        count = result.scalar_one()
        if count > 0:
            print(f"ℹ️  Platforms already seeded ({count}) — skipping")
            return
        for p in platforms:
            await db.execute(
                text("""
                    INSERT INTO platforms (id, name, type, schedule_cron, is_active)
                    VALUES (gen_random_uuid(), :name, :type, :schedule_cron, TRUE)
                """),
                p,
            )
        await db.commit()
        print(f"✅ Seeded {len(platforms)} platforms")


async def seed_admin() -> None:
    """Insert demo org + admin user if not present."""
    from app.core.security import hash_password

    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    now = datetime.now(tz=timezone.utc)
    pw_hash = hash_password("Admin1234!")

    async with SessionLocal() as db:
        # Check if admin already exists
        result = await db.execute(text("SELECT id FROM users WHERE email = 'admin@cat.demo'"))
        if result.scalar_one_or_none():
            print("ℹ️  Admin user already exists — skipping seed")
            return

        # Insert org
        await db.execute(
            text("""
                INSERT INTO organizations (id, name, slug, plan, created_at)
                VALUES (:id, :name, :slug, :plan, :created_at)
                ON CONFLICT (slug) DO NOTHING
            """),
            {"id": str(org_id), "name": "Demo Org", "slug": "demo", "plan": "pro", "created_at": now},
        )

        # Re-fetch org_id in case of conflict
        row = await db.execute(text("SELECT id FROM organizations WHERE slug = 'demo'"))
        org_id = row.scalar_one()

        # Insert admin user
        await db.execute(
            text("""
                INSERT INTO users (id, org_id, email, password_hash, role, failed_attempts, created_at, updated_at)
                VALUES (:id, :org_id, :email, :pw, :role, 0, :now, :now)
            """),
            {
                "id": str(user_id),
                "org_id": str(org_id),
                "email": "admin@cat.demo",
                "pw": pw_hash,
                "role": "admin",
                "now": now,
            },
        )

        await db.commit()
        print("✅ Seed complete:")
        print("   Email:    admin@cat.demo")
        print("   Password: Admin1234!")
        print("   Role:     admin")
        print(f"   Org:      Demo Org (id={org_id})")


async def main() -> None:
    await create_tables()
    await seed_platforms()
    await seed_admin()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
