# Pseudocode — Ozon Scraper

**SPARC Phase 4: Pseudocode** | Feature: ozon-scraper

---

## 1. Data Structures

```
ContentData { title, description, composition, image_url }   # shared with WB
PriceData   { price, original_price, discount_pct, promo_label }
StockData   { in_stock: bool, total_qty: int }
ReviewData  { external_review_id, review_text, rating: 1-5, review_date }

ScraperError(code: str, message: str)
  codes: NO_ITEM_ID | NOT_FOUND | RATE_LIMITED | API_UNAVAILABLE | PARSE_ERROR
```

---

## 2. Core Algorithms

### Algorithm: OzonScraper._fetch_product_page(item_id)

```
INPUT: item_id: str
OUTPUT: parsed widgetStates dict

1. url = COMPOSER_API
   params = {"url": f"/product/{item_id}/"}

2. resp = await self._get(url, params=params, headers=self._HEADERS)

3. IF resp.status_code == 429 OR resp.status_code == 403:
     RAISE httpx.HTTPStatusError → triggers retry in with_retry()

4. IF resp.status_code == 503 OR network error:
     RAISE ScraperError("API_UNAVAILABLE")

5. IF resp.status_code != 200:
     RAISE ScraperError("API_UNAVAILABLE")

6. data = resp.json()
   widgets = _parse_widget_states(data)

7. IF "webProductHeading-" NOT IN widgets:
     # Product doesn't exist or was delisted
     RAISE ScraperError("NOT_FOUND")

8. RETURN widgets
```

---

### Algorithm: OzonScraper.collect_content(item_id)

```
INPUT: item_id: str
OUTPUT: ContentData

1. widgets = await _fetch_product_page(item_id)

2. heading = widgets.get("webProductHeading-", {})
   title = sanitize(heading.get("title", ""), max_len=500)
   IF NOT title:
     RAISE ScraperError("PARSE_ERROR", "empty title")

3. sku_widget = widgets.get("webDetailSKU-", {})
   # description: try plaintext "description" first, then "richContent" (HTML)
   desc_plain = sku_widget.get("description", "")
   desc_rich  = sku_widget.get("richContent", "")
   description = sanitize(desc_plain or desc_rich, max_len=5000)

   # composition: look in characteristics for "Состав" entry
   composition = None
   for char in sku_widget.get("characteristics", []):
     if "состав" in char.get("name", "").lower():
       values = char.get("values", [])
       composition = sanitize(", ".join(str(v) for v in values), max_len=2000) or None
       break

4. gallery = widgets.get("webGallery-", {})
   images = gallery.get("images", [])
   image_url = images[0].get("url") if images else None
   # Validate against _OZ_IMAGE_CDN_RE — set None if fails (SSRF guard)
   IF image_url AND NOT _OZ_IMAGE_CDN_RE.match(image_url):
     LOG warning f"Image URL failed allowlist: {image_url}"
     image_url = None

5. RETURN ContentData(title=title, description=description,
                      composition=composition, image_url=image_url)
```

---

### Algorithm: OzonScraper.collect_price(item_id)

```
INPUT: item_id: str
OUTPUT: PriceData

1. widgets = await _fetch_product_page(item_id)

2. price_widget = widgets.get("webPrice-", {})
   price_data = price_widget.get("price", price_widget)  # some versions nest under "price"

   # Ozon uses "cardPrice" (club/promo price), falling back to "price"
   raw_price    = price_data.get("cardPrice") or price_data.get("price", "")
   raw_original = price_data.get("originalPrice") or raw_price
   promo_label  = price_data.get("promoText") or None

3. price    = _parse_price_str(raw_price)
   original = _parse_price_str(raw_original)

4. IF original == 0:
     # Widget absent or product unlisted — not a scraper error, return zeros
     RETURN PriceData(price=Decimal("0"), original_price=Decimal("0"),
                      discount_pct=Decimal("0"), promo_label=None)

5. IF price == 0:
     price = original  # club price widget absent — no discount

6. discount = (original - price) / original * 100 if original > price else Decimal("0")

7. RETURN PriceData(
     price=price.quantize(Decimal("0.01")),
     original_price=original.quantize(Decimal("0.01")),
     discount_pct=discount.quantize(Decimal("0.01")),
     promo_label=promo_label,
   )
```

---

### Algorithm: OzonScraper.collect_stock(item_id)

```
INPUT: item_id: str
OUTPUT: StockData

1. widgets = await _fetch_product_page(item_id)

2. cart_widget = widgets.get("webAddToCart-", {})

   # availability: 1 = available, 0 = out of stock
   availability = cart_widget.get("availability", 0)
   count = int(cart_widget.get("count", 0))

3. in_stock = (availability == 1 and count > 0)
   total_qty = count if in_stock else 0

4. RETURN StockData(in_stock=in_stock, total_qty=total_qty)
```

---

### Algorithm: OzonScraper.collect_reviews(item_id, take=50)

```
INPUT: item_id: str, take: int = 50
OUTPUT: list[ReviewData]

1. url = COMPOSER_API
   params = {"url": f"/product/{item_id}/reviews/", "page": 1}
   resp = await self._get(url, params=params, headers=self._HEADERS)
   resp.raise_for_status()
   data = resp.json()

2. widgets = _parse_widget_states(data)
   review_widget = widgets.get("webReviewList-", {})
   feedbacks = review_widget.get("reviews", [])

3. result = []
   FOR fb IN feedbacks[:take]:
     text = sanitize(fb.get("text", ""), max_len=5000)
     rating = max(1, min(5, int(fb.get("score", 5))))
     date_str = fb.get("publishedAt", fb.get("createdAt", ""))[:10]
     TRY:
       review_date = date.fromisoformat(date_str)
     EXCEPT ValueError:
       CONTINUE  # skip reviews with unparseable date

     result.append(ReviewData(
       external_review_id=str(fb.get("id", "")),
       review_text=text,
       rating=rating,
       review_date=review_date,
     ))

4. RETURN result
```

---

### Algorithm: collect_ozon_content (Celery task)

```
INPUT: sku_platform_id: str
SIDE EFFECTS: upserts content_scores row, uploads image to MinIO

1. # Extract primitives within session — NO ORM object survives session boundary
   WITH get_db_session() AS db:
     row = db.query(SKUPlatform.id, SKUPlatform.sku_id,
                    SKUPlatform.external_id, SKU.org_id)
            .join(SKU, SKU.id == SKUPlatform.sku_id)
            .filter(SKUPlatform.id == uuid.UUID(sku_platform_id))
            .first()
   IF row is None: RETURN
   sp_id, sku_id, item_id, org_id = row

2. IF item_id is None or item_id == "":
     LOG info "NO_ITEM_ID for {sku_platform_id}"
     RETURN

3. scraper = OzonScraper(proxy_rotator=get_proxy_rotator())
   TRY:
     content = asyncio.run(scraper.collect_content(item_id))
   EXCEPT ScraperError AS e:
     IF e.code == "NOT_FOUND": RETURN
     RAISE self.retry(exc=e, countdown=2**self.request.retries)

4. s3_key = None
   IF content.image_url:
     TRY:
       image_bytes = asyncio.run(_download_image_async(content.image_url, get_proxy_rotator().next()))
       s3_key = f"org/{org_id}/sku/{sku_id}/ozon/main.jpg"
       minio.upload(s3_key, image_bytes, "image/jpeg")
     EXCEPT Exception AS e:
       LOG warning "Image download failed: {e}"
       s3_key = None  # non-fatal

5. today = date.today()
   WITH get_db_session() AS db:
     existing = db.query(ContentScore)
                  .filter(ContentScore.sku_platform_id == sp_id,
                          ContentScore.scored_at == today)
                  .first()
     IF existing:
       existing.collected_title       = content.title
       existing.collected_description = content.description
       existing.collected_composition = content.composition
       existing.collected_image_url   = s3_key
     ELSE:
       db.add(ContentScore(
         sku_platform_id=sp_id, scored_at=today,
         collected_title=content.title,
         collected_description=content.description,
         collected_composition=content.composition,
         collected_image_url=s3_key,
       ))
```

---

### Algorithm: collect_ozon_price (Celery task)

```
INPUT: sku_platform_id: str

1. WITH get_db_session() AS db:
     row = db.query(SKUPlatform.id, SKUPlatform.external_id, SKU.org_id)
            .join(SKU, SKU.id == SKUPlatform.sku_id)
            .filter(SKUPlatform.id == uuid.UUID(sku_platform_id))
            .first()
   IF row is None: RETURN
   sp_id, item_id, org_id = row

2. IF item_id is None: RETURN

3. scraper = OzonScraper(proxy_rotator=get_proxy_rotator())
   TRY:
     price_data = asyncio.run(scraper.collect_price(item_id))
   EXCEPT ScraperError AS e:
     IF e.code == "NOT_FOUND": RETURN
     RAISE self.retry(exc=e, countdown=2**self.request.retries)

4. WITH get_db_session() AS db:
     db.add(PriceSnapshot(
       sku_platform_id=sp_id,
       price=price_data.price,
       original_price=price_data.original_price,
       discount_pct=price_data.discount_pct,
       promo_label=price_data.promo_label,
       collected_at=datetime.now(tz=timezone.utc),
     ))
```

---

### Algorithm: collect_ozon_stock (Celery task)

```
# Identical pattern to collect_ozon_price (steps 1-3),
# then upsert content_scores stock fields:

4. today = date.today()
   WITH get_db_session() AS db:
     existing = db.query(ContentScore)
                  .filter(ContentScore.sku_platform_id == sp_id,
                          ContentScore.scored_at == today)
                  .first()
     IF existing:
       existing.in_stock     = stock_data.in_stock
       existing.warehouse_qty = stock_data.total_qty
     ELSE:
       db.add(ContentScore(
         sku_platform_id=sp_id, scored_at=today,
         in_stock=stock_data.in_stock,
         warehouse_qty=stock_data.total_qty,
         # content fields remain NULL — partial-row contract
       ))
```

---

### Algorithm: collect_ozon_reviews (Celery task)

```
# Steps 1-3 same as price task
4. IF NOT reviews: RETURN

5. values = [
     {
       "id": uuid.uuid4(),
       "sku_platform_id": sp_id,
       "external_review_id": r.external_review_id,
       "review_text": r.review_text,
       "rating": r.rating,
       "review_date": r.review_date,
       "collected_at": datetime.now(tz=timezone.utc),
     }
     for r in reviews
     if r.external_review_id  # skip reviews with empty ID
   ]

6. WITH get_db_session() AS db:
     stmt = pg_insert(Review).values(values)
            .on_conflict_do_nothing(constraint="uq_reviews_sp_ext_id")
     db.execute(stmt)
   # Single bulk INSERT — no N+1 loop
```

---

## 3. Helper: _parse_widget_states(data)

```
INPUT: response JSON dict
OUTPUT: dict[str, dict] keyed by widget name prefix

FOR key, value IN data.get("widgetStates", {}).items():
  FOR prefix IN _KNOWN_WIDGETS:
    IF key.startswith(prefix):
      TRY:
        result[prefix] = json.loads(value)
      EXCEPT (json.JSONDecodeError, TypeError):
        PASS  # skip malformed widget — non-fatal
      BREAK
RETURN result
```

---

## 4. Helper: _parse_price_str(s)

```
INPUT: price string like "1 299 ₽" or "1\xa0299\xa0₽" or None
OUTPUT: Decimal

1. IF s is None or s == "": RETURN Decimal("0")
2. cleaned = replace "\xa0" → "" and " " → ""
3. cleaned = re.sub(r"[^\d.,]", "", cleaned)
4. cleaned = replace "," → "."
5. RETURN Decimal(cleaned) if cleaned else Decimal("0")
```
