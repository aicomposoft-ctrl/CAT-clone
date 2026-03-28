# Pseudocode: Lenta Scraper

## Module: lenta.py

### Constants

```
_LT_IMAGE_CDN_RE = re.compile(
    r"^https://lenta\.com/images/[A-Za-z0-9/_\-\.]+\.(jpg|jpeg|png|webp)$"
)
```

### LentaScraper(BaseScraper)

```
platform = "Lenta"
rate_limit = 1.0  # req/sec — conservative for traditional retailer
_BASE_API = "https://lenta.com/api/v1"
_HEADERS = {
    "User-Agent": "LentaApp/4.2.1 (Android)",
    "Accept": "application/json",
}
```

### collect_content(product_id) → ContentData

```
INPUT: product_id (validated numeric string)

data = await _fetch_product(product_id)

title = sanitize(data["name"], 500)
IF NOT title:
    RAISE ScraperError("PARSE_ERROR", "empty title")

description = sanitize(data.get("description") or "", 5000)
composition = sanitize(data.get("composition") or "", 2000) or None

image_url = None
images = data.get("images") or []
IF images AND images[0].get("url"):
    candidate = images[0]["url"]
    IF _LT_IMAGE_CDN_RE.match(candidate):
        image_url = candidate
    ELSE:
        logger.warning("image URL failed SSRF allowlist ... sku_platform=%s")
        # URL value NOT logged

RETURN ContentData(title, description, composition, image_url)
```

### collect_price(product_id) → PriceData

```
INPUT: product_id

data = await _fetch_product(product_id)

TRY:
    price = Decimal(data["price"]) / 100
    raw_original = data.get("originalPrice") or data["price"]
    original_price = Decimal(raw_original) / 100
EXCEPT (KeyError, InvalidOperation, TypeError):
    RAISE ScraperError("PARSE_ERROR", "price fields missing or non-numeric")

TRY:
    discount_pct = Decimal(data.get("discountPercent", 0))
EXCEPT (TypeError, InvalidOperation):
    discount_pct = Decimal(0)

promo_label = sanitize(data.get("promoLabel") or "", 200) or None

RETURN PriceData(
    price.quantize("0.01"),
    original_price.quantize("0.01"),
    discount_pct.quantize("0.01"),
    promo_label,
)
```

### collect_stock(product_id) → StockData

```
INPUT: product_id

data = await _fetch_product(product_id)

in_stock = bool(data.get("inStock", False))

TRY:
    total_qty = int(data.get("availableQuantity", 0))
EXCEPT (TypeError, ValueError):
    total_qty = 0

RETURN StockData(in_stock, total_qty)
```

### collect_reviews(product_id, take=50) → list[ReviewData]

```
INPUT: product_id, take

url = f"{_BASE_API}/products/{product_id}/reviews"
params = {"page": 1, "limit": take}

DEFINE _fetch():
    resp = await self._get(url, params=params, headers=_HEADERS)
    IF resp.status_code == 404:
        RETURN None  # sentinel — no reviews endpoint
    resp.raise_for_status()  # with_retry() handles 429, 5xx
    RETURN resp.json()

TRY:
    data = await self.with_retry(_fetch)
EXCEPT ScraperError:
    RAISE
EXCEPT Exception as exc:
    RAISE ScraperError("API_UNAVAILABLE", str(exc))

IF data is None:
    RETURN []

result = []
FOR fb IN (data.get("reviews") or []):
    external_id = str(fb.get("id", ""))[:200].strip()
    IF NOT external_id:
        CONTINUE

    text = sanitize(fb.get("text") or "", 5000)
    rating = _parse_rating(fb.get("rating", 5))
    review_date = _parse_review_date(fb.get("createdAt"))

    result.append(ReviewData(external_id, text, rating, review_date))

RETURN result
```

### _fetch_product(product_id) → dict

```
url = f"{_BASE_API}/products/{product_id}"

DEFINE _fetch():
    resp = await self._get(url, headers=_HEADERS)
    IF resp.status_code == 404:
        RAISE ScraperError("NOT_FOUND", f"product_id={product_id} not found")
    resp.raise_for_status()  # httpx.HTTPStatusError → with_retry retries 429/5xx
    RETURN resp.json()

TRY:
    RETURN await self.with_retry(_fetch)
EXCEPT ScraperError:
    RAISE
EXCEPT Exception as exc:
    RAISE ScraperError("API_UNAVAILABLE", str(exc))
```

## Module: lenta_content_task.py

```
@celery_app.task(bind=True, max_retries=3, name="lenta.collect_content")
FUNCTION collect_lenta_content(self, sku_platform_id: str):

  # Session 1 — read primitives
  WITH get_db_session() as db:
      row = db.query(SKUPlatform.id, SKUPlatform.sku_id, SKUPlatform.external_id, SKU.org_id)
               .join(SKU).filter(SKUPlatform.id == UUID(sku_platform_id)).first()

  IF row is None:
      logger.warning("... not found — skipping")
      RETURN

  sp_id, sku_id, raw_product_id, org_id = row

  TRY:
      product_id = _parse_product_id(raw_product_id)
  EXCEPT ValueError:          # NO_PRODUCT_ID
      logger.info("... NO_PRODUCT_ID — skipping")
      RETURN
  EXCEPT ScraperError:        # PARSE_ERROR
      logger.warning("... invalid product_id")
      RETURN

  scraper = LentaScraper(proxy_rotator=get_proxy_rotator())

  ASYNC _fetch_content_and_image():
      c = await scraper.collect_content(product_id)  # ScraperError propagates
      img = None
      IF c.image_url:
          TRY:
              img = await _download_image_async(c.image_url, get_proxy_rotator().next())
          EXCEPT Exception:
              PASS  # non-fatal, logged after asyncio.run
      RETURN c, img

  TRY:
      content, image_bytes = asyncio.run(_fetch_content_and_image())
  EXCEPT ScraperError as exc:
      IF exc.code == "NOT_FOUND":  RETURN
      logger.warning("... ScraperError code=%s", exc.code)
      RAISE self.retry(exc=exc, countdown=2**self.request.retries)

  # Upload image to MinIO (non-fatal)
  s3_key = None
  IF image_bytes is not None:
      TRY:
          s3_key = f"org/{org_id}/sku/{sku_id}/lenta/main.jpg"
          _get_minio().upload(s3_key, image_bytes, "image/jpeg")
      EXCEPT Exception:
          logger.warning("... MinIO upload failed", exc_info=True)
          s3_key = None
  ELIF content.image_url:
      logger.warning("... image download failed")

  # Session 2 — write
  now_utc = datetime.now(tz=timezone.utc)
  WITH get_db_session() as db:
      stmt = pg_insert(ContentScore).values(
          id=uuid4(), sku_platform_id=sp_id, scored_at=now_utc.date(),
          collected_title=content.title, collected_description=content.description,
          collected_composition=content.composition, collected_image_url=s3_key,
          created_at=now_utc,
      ).on_conflict_do_update(
          constraint="uq_content_scores_sp_date",
          set_={collected_title, collected_description, collected_composition, collected_image_url}
      )
      db.execute(stmt)
```

## Module: lenta_stock_task.py

```
@celery_app.task(bind=True, max_retries=3, name="lenta.collect_stock")
FUNCTION collect_lenta_stock(self, sku_platform_id: str):

  # Session 1 — read
  WITH get_db_session() as db:
      row = db.query(SKUPlatform.id, SKUPlatform.external_id, SKU.org_id)
               .join(SKU).filter(SKUPlatform.id == UUID(sku_platform_id)).first()
  ...validate...

  TRY:
      stock_data = asyncio.run(scraper.collect_stock(product_id))
  EXCEPT ScraperError as exc:
      IF exc.code == "NOT_FOUND": RETURN
      RAISE self.retry(...)

  # Session 2 — partial-row upsert
  now_utc = datetime.now(tz=timezone.utc)
  WITH get_db_session() as db:
      stmt = pg_insert(ContentScore).values(
          id=uuid4(), sku_platform_id=sp_id, scored_at=now_utc.date(),
          in_stock=stock_data.in_stock, warehouse_qty=stock_data.total_qty,
          created_at=now_utc,
      ).on_conflict_do_update(
          constraint="uq_content_scores_sp_date",
          set_={in_stock, warehouse_qty}
          # content fields INTENTIONALLY ABSENT
      )
      db.execute(stmt)
```

## Module: lenta_orchestrator.py

```
_LT_PLATFORM_NAME = "Lenta"

FUNCTION _load_lenta_sku_platform_ids(db) -> list[str]:
    RETURN [str(row.id) for row in
            db.query(SKUPlatform.id)
              .join(Platform).join(SKU)
              .filter(Platform.name == "Lenta",
                      Platform.is_active.is_(True),
                      SKUPlatform.is_monitored.is_(True))
              .all()]

@celery_app.task(name="lenta.collect_content_all")
FUNCTION collect_lenta_content_all():
    WITH get_db_session() as db:
        sp_ids = _load_lenta_sku_platform_ids(db)
    IF sp_ids:
        group(
            task
            FOR sp_id IN sp_ids
            FOR task IN (
                collect_lenta_content.s(sp_id),
                collect_lenta_stock.s(sp_id),
                collect_lenta_reviews.s(sp_id),
            )
        ).delay()   # single broker round-trip

@celery_app.task(name="lenta.collect_prices_all")
FUNCTION collect_lenta_prices_all():
    WITH get_db_session() as db:
        sp_ids = _load_lenta_sku_platform_ids(db)
    IF sp_ids:
        group(collect_lenta_price.s(sp_id) FOR sp_id IN sp_ids).delay()
```

## Error Handling Matrix

| Error | Source | Task action |
|-------|--------|-------------|
| `NO_PRODUCT_ID` | `_parse_product_id` raises `ValueError` | `logger.info` + return |
| `PARSE_ERROR` | `_parse_product_id` raises `ScraperError` | `logger.warning` + return |
| `NOT_FOUND` | `_fetch_product` HTTP 404 | `logger.info` + return |
| `RATE_LIMITED` | `with_retry` exhausted on 429 | `self.retry(countdown=2**retries)` |
| `API_UNAVAILABLE` | `with_retry` exhausted on 5xx/network | `self.retry(countdown=2**retries)` |
| Image download fail | `_download_image_async` any exception | `s3_key=None`, continue |
| MinIO upload fail | `minio.upload()` any exception | `s3_key=None`, continue, `exc_info=True` |
