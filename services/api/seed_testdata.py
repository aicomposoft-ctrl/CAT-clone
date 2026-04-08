"""
Test data seed: fills DB with realistic data for the existing SKU × Ozon.

Run: docker compose exec -w /app api python seed_testdata.py

Inserts (idempotent — skips if data already exists):
  - 30 days of content_scores (trending from 58 → 71)
  - 30 days of price_snapshots (base 189 RUB, small fluctuations + one promo)
  - 25 reviews (mix of ratings, Russian text, sentiment)
  - distribution_plan for current + last 4 weeks
  - stock_history for current + last 4 weeks
  - 1 alert_config (content_drop threshold 60)
  - 3 alert_events (2 content_drop, 1 oos)
"""

import asyncio
import os
import random
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

POSTGRES_URL = os.environ.get(
    "POSTGRES_URL",
    "postgresql+asyncpg://cat_user:cat_password@postgres:5432/cat_db",
)

engine = create_async_engine(POSTGRES_URL, echo=False)
DB = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

random.seed(42)


# ── Fetch context ─────────────────────────────────────────────────────────────

async def fetch_context(db: AsyncSession) -> dict:
    r = await db.execute(text("""
        SELECT s.id as sku_id, s.org_id, sp.id as sp_id, p.id as platform_id, p.name as platform_name
        FROM skus s
        JOIN sku_platforms sp ON sp.sku_id = s.id
        JOIN platforms p ON p.id = sp.platform_id
        WHERE s.is_active = TRUE
        LIMIT 1
    """))
    row = r.fetchone()
    if not row:
        raise RuntimeError("No SKU with linked platform found. Add a SKU and link it to a platform first.")
    return {
        "sku_id": str(row.sku_id),
        "org_id": str(row.org_id),
        "sp_id": str(row.sp_id),
        "platform_id": str(row.platform_id),
        "platform_name": row.platform_name,
    }


# ── Content scores (30 days) ──────────────────────────────────────────────────

async def seed_content_scores(db: AsyncSession, ctx: dict) -> None:
    r = await db.execute(text("SELECT COUNT(*) FROM content_scores WHERE sku_platform_id = :sp"), {"sp": ctx["sp_id"]})
    if r.scalar_one() > 0:
        print("ℹ️  content_scores already exist — skipping")
        return

    today = date.today()
    # Score trends: starts at 58, dips to 51 at day 20, recovers to 71
    base_scores = [58 + i * 0.4 + random.uniform(-2, 2) for i in range(30)]
    base_scores[20] = 51.0  # visible dip for alert trigger
    base_scores[21] = 53.0

    for i, total in enumerate(base_scores):
        scored_at = today - timedelta(days=29 - i)
        image = round(total * 0.38 / 40 + random.uniform(0.5, 1.5), 2)
        desc = round(total * 0.37 / 35 + random.uniform(0.3, 1.0), 2)
        comp = round(total - image * 40 / 100 - desc * 35 / 100, 2)
        await db.execute(text("""
            INSERT INTO content_scores
              (id, sku_platform_id, scored_at, collected_title, collected_description,
               in_stock, warehouse_qty, image_score, description_score, composition_score,
               content_total, created_at)
            VALUES
              (gen_random_uuid(), :sp, :date, :title, :desc,
               TRUE, :qty, :img, :desc_s, :comp_s, :total, NOW())
            ON CONFLICT (sku_platform_id, scored_at) DO NOTHING
        """), {
            "sp": ctx["sp_id"],
            "date": scored_at,
            "title": "Молоко 3.2%, 950мл ТФА/тетрапак",
            "desc": "Молоко пастеризованное 3,2% жирности. Производитель: ТФА. Объём: 950 мл.",
            "qty": random.randint(50, 500),
            "img": round(max(0.4, min(1.0, total / 100 + random.uniform(-0.05, 0.05))), 2),
            "desc_s": round(max(0.4, min(1.0, total / 100 + random.uniform(-0.05, 0.05))), 2),
            "comp_s": round(max(0.4, min(1.0, total / 100 + random.uniform(-0.05, 0.05))), 2),
            "total": round(max(0, min(100, total)), 2),
        })

    await db.commit()
    print(f"✅ content_scores: 30 дней (последний score: {round(base_scores[-1], 1)})")


# ── Price snapshots (30 days, 2x per day) ────────────────────────────────────

async def seed_prices(db: AsyncSession, ctx: dict) -> None:
    r = await db.execute(text("SELECT COUNT(*) FROM price_snapshots WHERE sku_platform_id = :sp"), {"sp": ctx["sp_id"]})
    if r.scalar_one() > 0:
        print("ℹ️  price_snapshots already exist — skipping")
        return

    today = date.today()
    base_price = 189.0

    for i in range(30):
        day = today - timedelta(days=29 - i)
        # Promo on days 10-15
        is_promo = 10 <= i <= 15
        price = round(base_price * (0.82 if is_promo else 1.0) + random.uniform(-3, 3), 2)
        original = base_price + random.uniform(-1, 1)
        discount = round((1 - price / original) * 100, 2) if original > price else 0.0

        for hour in [9, 18]:
            collected_at = datetime(day.year, day.month, day.day, hour, 0, tzinfo=timezone.utc)
            await db.execute(text("""
                INSERT INTO price_snapshots
                  (id, sku_platform_id, price, original_price, discount_pct, promo_label, collected_at)
                VALUES
                  (gen_random_uuid(), :sp, :price, :orig, :disc, :promo, :at)
            """), {
                "sp": ctx["sp_id"],
                "price": price,
                "orig": round(original, 2),
                "disc": discount,
                "promo": "Акция" if is_promo else None,
                "at": collected_at,
            })

    await db.commit()
    print("✅ price_snapshots: 30 дней × 2 снапшота (промо на днях 10-15)")


# ── Reviews ───────────────────────────────────────────────────────────────────

REVIEWS = [
    (5, "positive", 0.91, "Отличное молоко! Покупаю уже несколько месяцев, качество стабильное. Доставка быстрая."),
    (5, "positive", 0.87, "Свежее, вкусное. Дети в восторге. Рекомендую всем."),
    (4, "positive", 0.78, "Хорошее молоко, но упаковка иногда приходит помятая. В целом доволен."),
    (5, "positive", 0.92, "Беру постоянно. Качество не меняется, цена адекватная."),
    (3, "neutral", 0.61, "Молоко как молоко. Ничего особенного, но и не плохое."),
    (4, "positive", 0.80, "Хороший продукт. Срок годности всегда свежий."),
    (1, "negative", 0.89, "Пришло прокисшее. Срок годности ещё 5 дней, но уже скисло. Разочарован."),
    (5, "positive", 0.94, "Лучшее молоко на Озоне! Беру ящиками."),
    (2, "negative", 0.82, "Вкус немного отличается от привычного. Не понравилось."),
    (4, "positive", 0.75, "Нормальное молоко по хорошей цене. Доставили быстро."),
    (5, "positive", 0.88, "Свежее, не водянистое. Рекомендую!"),
    (3, "neutral", 0.55, "Среднее качество. Бывало и лучше."),
    (5, "positive", 0.93, "Отличный продукт! Всегда беру именно это молоко."),
    (1, "negative", 0.91, "Ужасная упаковка — протекает. Уже второй раз такое. Больше не закажу."),
    (4, "positive", 0.77, "Качество хорошее, цена немного выросла, но всё равно беру."),
    (5, "positive", 0.85, "Дети пьют с удовольствием. Натуральный вкус."),
    (2, "negative", 0.79, "Слишком водянистое для 3.2%. Ожидал большего."),
    (4, "positive", 0.81, "Хороший продукт, беру регулярно. Упаковка удобная."),
    (3, "neutral", 0.58, "Обычное молоко. Ни хорошо ни плохо."),
    (5, "positive", 0.90, "Свежее, вкусное! Срок годности 14 дней — это плюс."),
    (4, "positive", 0.76, "Молоко как молоко, но качество стабильное. Беру уже год."),
    (1, "negative", 0.86, "Пришло с истёкшим сроком годности. Возврат оформил."),
    (5, "positive", 0.89, "Отличное соотношение цены и качества!"),
    (3, "neutral", 0.60, "Нормальное. Не хуже других марок в этой ценовой категории."),
    (4, "positive", 0.82, "Берём всей семьёй. Качество устраивает."),
]

async def seed_reviews(db: AsyncSession, ctx: dict) -> None:
    r = await db.execute(text("SELECT COUNT(*) FROM reviews WHERE sku_platform_id = :sp"), {"sp": ctx["sp_id"]})
    if r.scalar_one() > 0:
        print("ℹ️  reviews already exist — skipping")
        return

    today = date.today()
    for i, (rating, sentiment, score, text_) in enumerate(REVIEWS):
        review_date = today - timedelta(days=random.randint(1, 29))
        await db.execute(text("""
            INSERT INTO reviews
              (id, sku_platform_id, external_review_id, review_text, rating,
               review_date, collected_at, sentiment, sentiment_score)
            VALUES
              (gen_random_uuid(), :sp, :ext_id, :txt, :rating,
               :rdate, NOW(), :sent, :score)
        """), {
            "sp": ctx["sp_id"],
            "ext_id": f"ozon-rev-{i+1001}",
            "txt": text_,
            "rating": rating,
            "rdate": review_date,
            "sent": sentiment,
            "score": round(score, 3),
        })

    await db.commit()
    print(f"✅ reviews: {len(REVIEWS)} отзывов (+ и - смешаны)")


# ── Distribution plan + stock_history (5 weeks) ───────────────────────────────

def iso_week(d: date) -> tuple[int, int]:
    iso = d.isocalendar()
    return iso[1], iso[0]  # week, year


async def seed_distribution(db: AsyncSession, ctx: dict) -> None:
    r = await db.execute(text("SELECT COUNT(*) FROM distribution_plans WHERE sku_id = :sku"), {"sku": ctx["sku_id"]})
    if r.scalar_one() > 0:
        print("ℹ️  distribution_plans already exist — skipping")
        return

    today = date.today()
    for w in range(5):
        d = today - timedelta(weeks=w)
        week, year = iso_week(d)
        plan = random.randint(280, 350)
        await db.execute(text("""
            INSERT INTO distribution_plans (id, sku_id, platform_id, group_name, week_number, year, plan_tt_count)
            VALUES (gen_random_uuid(), :sku, :platform, :group_name, :week, :year, :plan)
            ON CONFLICT (sku_id, platform_id, week_number, year) DO NOTHING
        """), {"sku": ctx["sku_id"], "platform": ctx["platform_id"],
               "group_name": "Молочные продукты", "week": week, "year": year, "plan": plan})

        # stock_history: 85-97% of plan
        fact = int(plan * random.uniform(0.85, 0.97))
        collected_at = datetime(d.year, d.month, d.day, 8, 0, tzinfo=timezone.utc)
        await db.execute(text("""
            INSERT INTO stock_history (id, org_id, sku_id, platform_id, week_number, year, stock_count, collected_at)
            VALUES (gen_random_uuid(), :org, :sku, :platform, :week, :year, :fact, :at)
            ON CONFLICT DO NOTHING
        """), {
            "org": ctx["org_id"], "sku": ctx["sku_id"], "platform": ctx["platform_id"],
            "week": week, "year": year, "fact": fact, "at": collected_at,
        })

    await db.commit()
    print("✅ distribution_plans + stock_history: 5 недель (покрытие ~90%)")


# ── Alert config + events ─────────────────────────────────────────────────────

async def seed_alerts(db: AsyncSession, ctx: dict) -> None:
    r = await db.execute(text("SELECT id FROM alert_configs WHERE org_id = :org LIMIT 1"), {"org": ctx["org_id"]})
    config_row = r.fetchone()

    if config_row is None:
        config_id = str(uuid.uuid4())
        import json
        await db.execute(text("""
            INSERT INTO alert_configs
              (id, org_id, sku_id, platform_id, alert_type, threshold, email_recipients, is_active, created_at)
            VALUES
              (:id, :org, NULL, NULL, 'content_drop', 60.0, :emails, TRUE, NOW())
        """), {
            "id": config_id,
            "org": ctx["org_id"],
            "emails": json.dumps(["admin@cat.demo"]),
        })
        await db.commit()
        print("✅ alert_config: content_drop threshold=60")
    else:
        config_id = str(config_row.id)
        print("ℹ️  alert_config already exists")

    r = await db.execute(text("SELECT COUNT(*) FROM alert_events WHERE org_id = :org"), {"org": ctx["org_id"]})
    if r.scalar_one() > 0:
        print("ℹ️  alert_events already exist — skipping")
        return

    today = date.today()
    events = [
        {"alert_type": "content_drop", "days_ago": 9, "before": 63.4, "after": 51.0, "is_sent": True},
        {"alert_type": "content_drop", "days_ago": 8, "before": 51.0, "after": 53.0, "is_sent": True},
        {"alert_type": "oos",          "days_ago": 1, "before": None,  "after": None,  "is_sent": False},
    ]

    for e in events:
        days_ago = e["days_ago"]
        scored_at = today - timedelta(days=days_ago)
        triggered_at = datetime(scored_at.year, scored_at.month, scored_at.day, 6, 0, tzinfo=timezone.utc)
        await db.execute(text("""
            INSERT INTO alert_events
              (id, org_id, config_id, sku_platform_id, scored_at, alert_type,
               value_before, value_after, triggered_at, is_sent)
            VALUES
              (gen_random_uuid(), :org, :cfg, :sp, :scored_at, :atype,
               :before, :after, :at, :sent)
            ON CONFLICT (config_id, sku_platform_id, scored_at) DO NOTHING
        """), {
            "org": ctx["org_id"],
            "cfg": config_id,
            "sp": ctx["sp_id"],
            "scored_at": scored_at,
            "atype": e["alert_type"],
            "before": e["before"],
            "after": e["after"],
            "at": triggered_at,
            "sent": e["is_sent"],
        })

    await db.commit()
    print("✅ alert_events: 2 content_drop (sent) + 1 oos (active/unsent)")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    async with DB() as db:
        ctx = await fetch_context(db)
        print(f"\n📦 SKU: {ctx['sku_id'][:8]}... | Platform: {ctx['platform_name']} | Org: {ctx['org_id'][:8]}...\n")

    async with DB() as db:
        ctx = await fetch_context(db)
        await seed_content_scores(db, ctx)

    async with DB() as db:
        ctx = await fetch_context(db)
        await seed_prices(db, ctx)

    async with DB() as db:
        ctx = await fetch_context(db)
        await seed_reviews(db, ctx)

    async with DB() as db:
        ctx = await fetch_context(db)
        await seed_distribution(db, ctx)

    async with DB() as db:
        ctx = await fetch_context(db)
        await seed_alerts(db, ctx)

    await engine.dispose()
    print("\n🎉 Готово! Обнови страницы в браузере.")


if __name__ == "__main__":
    asyncio.run(main())
