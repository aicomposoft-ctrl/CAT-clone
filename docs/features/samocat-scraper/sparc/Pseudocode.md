# Pseudocode — Самокат Scraper

**Feature:** Самокат Scraper
**SPARC Phase:** Pseudocode

---

## 1. Core Data Structures

```
SamokatProductResponse:
  id: int
  name: str
  description: str | None
  composition: str | None
  images: list[{url: str}]
  price: int           ← kopeks
  originalPrice: int   ← kopeks
  discountPercent: int
  promoLabel: str | None
  inStock: bool
  availableQuantity: int

SamokatReview:
  id: str
  text: str | None
  rating: int
  createdAt: str       ← ISO8601
```

---

## 2. _parse_product_id

```
FUNCTION _parse_product_id(raw: str | None) -> str
  IF raw is None OR raw.strip() == "":
    RAISE ValueError("NO_PRODUCT_ID")
  stripped = raw.strip()
  IF NOT stripped.isdigit():
    RAISE ScraperError("PARSE_ERROR", f"not numeric: {stripped!r}")
  RETURN stripped
```

---

## 3. SamokatScraper.collect_content

```
ASYNC FUNCTION collect_content(product_id: str) -> ContentData
  url = f"{_BASE_API}/items/{product_id}"

  response = AWAIT with_retry(() => _get(url, headers=_HEADERS))

  IF response.status_code == 404:
    RAISE ScraperError("NOT_FOUND")
  IF response.status_code != 200:
    RAISE ScraperError("API_UNAVAILABLE", str(response.status_code))

  data = response.json()

  title = sanitize(data.get("name", ""), 500)
  description = sanitize(data.get("description") or "", 5000)
  composition = sanitize(data.get("composition") or "", 2000) or None

  image_url = None
  images = data.get("images") or []
  IF images AND images[0].get("url"):
    candidate = images[0]["url"]
    IF _SK_IMAGE_CDN_RE.match(candidate):
      image_url = candidate
    ELSE:
      LOG warning "image URL failed SSRF allowlist for product_id={product_id}"

  RETURN ContentData(
    title=title,
    description=description,
    composition=composition,
    image_url=image_url,
  )
```

---

## 4. SamokatScraper.collect_price

```
ASYNC FUNCTION collect_price(product_id: str) -> PriceData
  url = f"{_BASE_API}/items/{product_id}"

  response = AWAIT with_retry(() => _get(url, headers=_HEADERS))

  IF response.status_code == 404:
    RAISE ScraperError("NOT_FOUND")

  data = response.json()

  TRY:
    price = Decimal(data["price"]) / 100
    original_price = Decimal(data.get("originalPrice") or data["price"]) / 100
  EXCEPT (KeyError, InvalidOperation, TypeError):
    RAISE ScraperError("PARSE_ERROR", "price fields missing or non-numeric")

  TRY:
    discount_pct = Decimal(data.get("discountPercent", 0))
  EXCEPT (TypeError, InvalidOperation):
    discount_pct = Decimal(0)

  promo_label = sanitize(data.get("promoLabel") or "", 200) or None

  RETURN PriceData(
    price=price,
    original_price=original_price,
    discount_pct=discount_pct,
    promo_label=promo_label,
  )
```

---

## 5. SamokatScraper.collect_stock

```
ASYNC FUNCTION collect_stock(product_id: str) -> StockData
  url = f"{_BASE_API}/items/{product_id}"

  response = AWAIT with_retry(() => _get(url, headers=_HEADERS))

  IF response.status_code == 404:
    RAISE ScraperError("NOT_FOUND")

  data = response.json()

  in_stock = bool(data.get("inStock", False))
  TRY:
    total_qty = int(data.get("availableQuantity", 0))
  EXCEPT (TypeError, ValueError):
    total_qty = 0

  RETURN StockData(in_stock=in_stock, total_qty=total_qty)  # total_qty → warehouse_qty in DB
```

---

## 6. SamokatScraper.collect_reviews

```
ASYNC FUNCTION collect_reviews(product_id: str, take: int = 50) -> list[ReviewData]
  url = f"{_BASE_API}/items/{product_id}/reviews"
  params = {"page": 1, "limit": take}

  response = AWAIT with_retry(() => _get(url, params=params, headers=_HEADERS))

  IF response.status_code == 404:
    RETURN []  ← product may exist but have no reviews endpoint

  data = response.json()
  raw_reviews = data.get("reviews") or []

  result = []
  FOR fb IN raw_reviews:
    external_id = str(fb.get("id", ""))
    IF NOT external_id:
      CONTINUE

    text = sanitize(fb.get("text") or "", 5000)

    TRY:
      rating = max(1, min(5, int(fb.get("rating", 5))))
    EXCEPT (TypeError, ValueError):
      rating = 5

    date_str = (fb.get("createdAt") or "")[:10]
    TRY:
      review_date = date.fromisoformat(date_str)
    EXCEPT ValueError:
      review_date = date.today()

    result.append(ReviewData(
      external_review_id=external_id,
      review_text=text,
      rating=rating,
      review_date=review_date,
    ))

  RETURN result
```

---

## 7. collect_samocat_content Task

```
TASK collect_samocat_content(sku_platform_id: str) -> None

  # Session 1: load primitives
  WITH get_db_session() AS db:
    row = db.query(
      SKUPlatform.id, SKUPlatform.sku_id, SKUPlatform.external_id, SKU.org_id
    ).join(SKU).filter(SKUPlatform.id == UUID(sku_platform_id)).first()

  IF row is None:
    LOG warning "sku_platform {sku_platform_id} not found — skipping"
    RETURN

  sp_id, sku_id, raw_product_id, org_id = row

  TRY:
    product_id = _parse_product_id(raw_product_id)
  EXCEPT ValueError:  # NO_PRODUCT_ID
    LOG info "NO_PRODUCT_ID — skipping"
    RETURN
  EXCEPT ScraperError:  # PARSE_ERROR
    LOG warning "invalid product_id"
    RETURN

  scraper = SamokatScraper(proxy_rotator=get_proxy_rotator())

  TRY:
    content = asyncio.run(scraper.collect_content(product_id))
  EXCEPT ScraperError AS exc:
    IF exc.code == "NOT_FOUND":
      LOG info "product not found — skipping"
      RETURN
    LOG warning f"ScraperError code={exc.code}"
    RAISE self.retry(exc=exc, countdown=2 ** self.request.retries)

  # Image download (non-fatal)
  s3_key = None
  IF content.image_url:
    TRY:
      proxy = get_proxy_rotator().next()
      image_bytes = asyncio.run(_download_image_async(content.image_url, proxy))
      s3_key = f"org/{org_id}/sku/{sku_id}/samocat/main.jpg"
      _get_minio().upload(s3_key, image_bytes, "image/jpeg")
    EXCEPT Exception:
      LOG warning "image download failed"
      s3_key = None

  # Session 2: upsert
  now_utc = datetime.now(tz=timezone.utc)
  WITH get_db_session() AS db:
    stmt = pg_insert(ContentScore).values(
      id=uuid4(), sku_platform_id=sp_id, scored_at=now_utc.date(),
      collected_title=content.title, collected_description=content.description,
      collected_composition=content.composition, collected_image_url=s3_key,
      created_at=now_utc,
    ).on_conflict_do_update(
      constraint="uq_content_scores_sp_date",
      set_={
        "collected_title": content.title,
        "collected_description": content.description,
        "collected_composition": content.composition,
        "collected_image_url": s3_key,
      }
    )
    db.execute(stmt)

  LOG info f"collect_samocat_content: done product_id={product_id}"
```

---

## 8. collect_samocat_stock Task

```
TASK collect_samocat_stock(sku_platform_id: str) -> None

  # Session 1: load primitives
  WITH get_db_session() AS db:
    row = db.query(SKUPlatform.id, SKUPlatform.external_id, SKU.org_id)
           .join(SKU).filter(SKUPlatform.id == UUID(sku_platform_id)).first()

  IF row is None:
    LOG warning "sku_platform {sku_platform_id} not found — skipping"
    RETURN

  sp_id, raw_product_id, org_id = row

  TRY:
    product_id = _parse_product_id(raw_product_id)
  EXCEPT ValueError:
    LOG info "NO_PRODUCT_ID — skipping"
    RETURN
  EXCEPT ScraperError:
    LOG warning "invalid product_id for sku_platform {sku_platform_id}"
    RETURN

  scraper = SamokatScraper(proxy_rotator=get_proxy_rotator())

  TRY:
    stock = asyncio.run(scraper.collect_stock(product_id))
  EXCEPT ScraperError AS exc:
    IF exc.code == "NOT_FOUND":
      LOG info "product not found — skipping"
      RETURN
    LOG warning f"ScraperError code={exc.code} sku_platform={sku_platform_id}"
    RAISE self.retry(exc=exc, countdown=2 ** self.request.retries)

  # Session 2: partial-row upsert
  # ONLY stock fields in set_ — content fields must NOT be overwritten
  now_utc = datetime.now(tz=timezone.utc)
  WITH get_db_session() AS db:
    stmt = (
      pg_insert(ContentScore)
      .values(
        id=uuid4(), sku_platform_id=sp_id, scored_at=now_utc.date(),
        in_stock=stock.in_stock, warehouse_qty=stock.total_qty,
        created_at=now_utc,
      )
      .on_conflict_do_update(
        constraint="uq_content_scores_sp_date",
        set_={
          "in_stock": stock.in_stock,
          "warehouse_qty": stock.total_qty,
          # content fields intentionally absent — partial-row contract
        }
      )
    )
    db.execute(stmt)

  LOG info f"collect_samocat_stock: done sku_platform={sku_platform_id}"
```

---

## 9. collect_samocat_price Task

```
TASK collect_samocat_price(sku_platform_id: str) -> None

  # Session 1: load primitives
  WITH get_db_session() AS db:
    row = db.query(SKUPlatform.id, SKUPlatform.external_id, SKU.org_id)
           .join(SKU).filter(SKUPlatform.id == UUID(sku_platform_id)).first()

  IF row is None: RETURN
  sp_id, raw_product_id, org_id = row

  product_id = _parse_product_id(raw_product_id)  # raises → skip or retry

  scraper = SamokatScraper(proxy_rotator=get_proxy_rotator())
  price_data = asyncio.run(scraper.collect_price(product_id))
  # ScraperError → self.retry()

  # Session 2: insert
  now_utc = datetime.now(tz=timezone.utc)
  WITH get_db_session() AS db:
    db.add(PriceSnapshot(
      id=uuid4(), sku_platform_id=sp_id,
      price=price_data.price, original_price=price_data.original_price,
      discount_pct=price_data.discount_pct, promo_label=price_data.promo_label,
      collected_at=now_utc,
    ))
```

---

## 9. collect_samocat_reviews Task

```
TASK collect_samocat_reviews(sku_platform_id: str) -> None

  # Session 1: load primitives
  WITH get_db_session() AS db:
    row = load_row(sku_platform_id)
  sp_id, raw_product_id, org_id = row

  product_id = _parse_product_id(raw_product_id)

  scraper = SamokatScraper(proxy_rotator=get_proxy_rotator())
  reviews = asyncio.run(scraper.collect_reviews(product_id))

  IF NOT reviews: RETURN

  # Session 2: bulk upsert
  now_utc = datetime.now(tz=timezone.utc)
  WITH get_db_session() AS db:
    FOR rev IN reviews:
      stmt = pg_insert(Review).values(
        id=uuid4(), sku_platform_id=sp_id,
        external_review_id=rev.external_review_id,
        review_text=rev.review_text, rating=rev.rating,
        review_date=rev.review_date, created_at=now_utc,
      ).on_conflict_do_update(
        constraint="uq_reviews_sp_external",
        set_={"review_text": rev.review_text, "rating": rev.rating},
      )
      db.execute(stmt)
```
