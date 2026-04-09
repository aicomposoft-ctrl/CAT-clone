-- ClickHouse schema for CAT analytics (time-series data)

CREATE DATABASE IF NOT EXISTS cat_analytics;

-- Price snapshots: daily price per SKU per platform
CREATE TABLE IF NOT EXISTS cat_analytics.price_snapshots (
    id          UUID DEFAULT generateUUIDv4(),
    org_id      UUID NOT NULL,
    sku_id      UUID NOT NULL,
    platform_id String NOT NULL,
    price       Decimal(12,2) NOT NULL,
    old_price   Nullable(Decimal(12,2)),
    in_stock    UInt8 DEFAULT 1,
    scraped_at  DateTime NOT NULL,
    date        Date MATERIALIZED toDate(scraped_at)
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (org_id, sku_id, platform_id, scraped_at);

-- Stock snapshots: daily stock level per SKU per platform
CREATE TABLE IF NOT EXISTS cat_analytics.stock_snapshots (
    id          UUID DEFAULT generateUUIDv4(),
    org_id      UUID NOT NULL,
    sku_id      UUID NOT NULL,
    platform_id String NOT NULL,
    stock_qty   Int32 DEFAULT 0,
    is_listed   UInt8 DEFAULT 1,
    scraped_at  DateTime NOT NULL,
    date        Date MATERIALIZED toDate(scraped_at)
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (org_id, sku_id, platform_id, scraped_at);

-- Content scores: ML-scored content per SKU per platform
CREATE TABLE IF NOT EXISTS cat_analytics.content_scores (
    id              UUID DEFAULT generateUUIDv4(),
    org_id          UUID NOT NULL,
    sku_id          UUID NOT NULL,
    platform_id     String NOT NULL,
    image_score     Float32 DEFAULT 0,
    desc_score      Float32 DEFAULT 0,
    comp_score      Float32 DEFAULT 0,
    content_total   Float32 DEFAULT 0,
    scored_at       DateTime NOT NULL,
    date            Date MATERIALIZED toDate(scored_at)
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (org_id, sku_id, platform_id, scored_at);

-- Review aggregates: daily sentiment per SKU per platform
CREATE TABLE IF NOT EXISTS cat_analytics.review_aggregates (
    id              UUID DEFAULT generateUUIDv4(),
    org_id          UUID NOT NULL,
    sku_id          UUID NOT NULL,
    platform_id     String NOT NULL,
    review_count    Int32 DEFAULT 0,
    avg_rating      Float32 DEFAULT 0,
    positive_count  Int32 DEFAULT 0,
    negative_count  Int32 DEFAULT 0,
    neutral_count   Int32 DEFAULT 0,
    aggregated_at   DateTime NOT NULL,
    date            Date MATERIALIZED toDate(aggregated_at)
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (org_id, sku_id, platform_id, aggregated_at);
