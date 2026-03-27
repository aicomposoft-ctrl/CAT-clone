# Pseudocode — Wildberries Scraper

**SPARC Phase 4: Pseudocode** | Feature: wb-scraper

---

## 1. Data Structures

```
ContentData { title, description, composition, image_url }
PriceData   { price, original_price, discount_pct, promo_label }
StockData   { in_stock: bool, total_qty: int }
ReviewData  { external_review_id, review_text, rating: 1-5, review_date }

ScraperError(code: str, message: str)
  codes: NO_NM_ID | NOT_FOUND | RATE_LIMITED | API_UNAVAILABLE | PARSE_ERROR
```

---

## 2. Algorithms

### Algorithm: collect_wb_content (Celery task)

```
INPUT: sku_platform_id: str
SIDE EFFECTS: upserts content_scores row, uploads image to S3

1. db = get_sync_db_session()
   sp = db.query(SKUPlatform).join(SKU).filter(SKUPlatform.id == sku_platform_id).first()
   IF sp is None:
     LOG warning "sku_platform not found", RETURN

2. nm_id = sp.external_id
   IF nm_id is None or nm_id == "":
     LOG info "NO_NM_ID for sku_platform {sku_platform_id}", RETURN  # silent skip

3. scraper = WildberriesScraper(proxy_rotator=ProxyRotator.from_env())

4. TRY:
     content = asyncio.run(scraper.collect_content(nm_id))
   EXCEPT ScraperError as e:
     IF e.code == "NOT_FOUND":
       LOG info "WB product {nm_id} not found — skipping"
       RETURN
     RAISE  # triggers Celery retry

5. s3_key = None
   IF content.image_url:
     TRY:
       image_bytes = httpx.get(content.image_url, timeout=30).content
       ext = ".jpg"
       s3_key = f"org/{sp.sku.org_id}/sku/{sp.sku_id}/wb/main{ext}"
       minio.upload(s3_key, image_bytes, "image/jpeg")
     EXCEPT Exception as e:
       LOG warning f"Image download failed for {nm_id}: {e}"
       s3_key = None  # non-fatal

6. today = date.today()
   existing = db.query(ContentScore).filter(
     ContentScore.sku_platform_id == sp.id,
     ContentScore.scored_at == today
   ).first()

   IF existing:
     existing.collected_image_url = s3_key
     existing.collected_description = content.description
     existing.collected_composition = content.composition
   ELSE:
     row = ContentScore(
       sku_platform_id=sp.id,
       scored_at=today,
       collected_image_url=s3_key,
       collected_description=content.description,
       collected_composition=content.composition,
     )
     db.add(row)
   db.commit()
```

---

### Algorithm: collect_wb_price (Celery task)

```
INPUT: sku_platform_id: str

1. sp = load_sku_platform(sku_platform_id)
   nm_id = validate_nm_id(sp)  # raises / returns early if None

2. scraper = WildberriesScraper(proxy_rotator=ProxyRotator.from_env())

3. TRY:
     price_data = asyncio.run(scraper.collect_price(nm_id))
   EXCEPT ScraperError as e:
     handle_error(e)

4. row = PriceSnapshot(
     sku_platform_id=sp.id,
     price=price_data.price,
     original_price=price_data.original_price,
     discount_pct=price_data.discount_pct,
     promo_label=price_data.promo_label,
     collected_at=datetime.utcnow(),
   )
   db.add(row)
   db.commit()
```

---

### Algorithm: collect_wb_stock (Celery task)

```
INPUT: sku_platform_id: str

1. sp = load_sku_platform(sku_platform_id)
   nm_id = validate_nm_id(sp)

2. scraper = WildberriesScraper(proxy_rotator=ProxyRotator.from_env())
   stock_data = asyncio.run(scraper.collect_stock(nm_id))

3. today = date.today()
   existing = db.query(ContentScore).filter(
     ContentScore.sku_platform_id == sp.id,
     ContentScore.scored_at == today,
   ).first()

   IF existing:
     existing.in_stock = stock_data.in_stock
   ELSE:
     db.add(ContentScore(
       sku_platform_id=sp.id,
       scored_at=today,
       in_stock=stock_data.in_stock,
     ))
   db.commit()
```

---

### Algorithm: collect_wb_reviews (Celery task)

```
INPUT: sku_platform_id: str

1. sp = load_sku_platform(sku_platform_id)
   nm_id = validate_nm_id(sp)

2. scraper = WildberriesScraper(proxy_rotator=ProxyRotator.from_env())
   reviews = asyncio.run(scraper.collect_reviews(nm_id, take=50))

3. FOR review IN reviews:
     # ON CONFLICT (sku_platform_id, external_review_id) DO NOTHING
     stmt = pg_insert(Review).values(
       sku_platform_id=sp.id,
       external_review_id=review.external_review_id,
       review_text=review.review_text,
       rating=review.rating,
       review_date=review.review_date,
       collected_at=datetime.utcnow(),
     ).on_conflict_do_nothing(constraint="uq_reviews_sp_ext_id")
     db.execute(stmt)
   db.commit()
```

---

### Algorithm: WildberriesScraper.collect_content

```
INPUT: nm_id: str
OUTPUT: ContentData

1. url = "https://card.wb.ru/cards/v2/detail"
   params = {appType: "1", curr: "rub", dest: "-1257786", nm: nm_id}

2. resp = await self._get(url, params=params)
   IF resp.status_code == 404 OR (200 AND products list empty):
     RAISE ScraperError("NOT_FOUND")
   IF resp.status_code == 429:
     RAISE httpx.HTTPStatusError (triggers retry)

3. data = resp.json()
   products = data.get("data", {}).get("products", [])
   IF NOT products:
     RAISE ScraperError("NOT_FOUND")
   product = products[0]

4. image_url = _build_image_url(nm_id, product)
   # WB image CDN formula:
   # nm_id → vol = nm_id // 100000, part = nm_id // 1000
   # basket = _select_basket(vol)  # lookup table: vol ranges → basket number 01-20
   # url = f"https://basket-{basket:02d}.wbbasket.ru/vol{vol}/part{part}/{nm_id}/images/big/1.jpg"

5. RETURN ContentData(
     title=sanitize(product.get("name", ""), 500),
     description=sanitize(product.get("description", ""), 5000),
     composition=sanitize(product.get("composition", ""), 2000) or None,
     image_url=image_url,
   )
```

---

### Helper: sanitize(text, max_len)

```
1. text = html.unescape(text)
2. text = re.sub(r"<[^>]+>", "", text)    # strip HTML tags
3. text = re.sub(r"\s+", " ", text).strip()
4. RETURN text[:max_len] if len(text) > max_len else text
```

---

### Helper: _build_image_url(nm_id, product)

```
# WB basket selection: deterministic based on vol
BASKET_MAP = [
    (143, 1), (287, 2), (431, 3), (719, 4), (1007, 5),
    (1061, 6), (1115, 7), (1169, 8), (1313, 9), (1601, 10),
    (1655, 11), (1919, 12), (2045, 13), (2189, 14), (2405, 15),
    (2621, 16), (2837, 17), (3053, 18), (3269, 19), (float("inf"), 20),
]

nm = int(nm_id)
vol = nm // 100000
part = nm // 1000
basket = next(b for (limit, b) in BASKET_MAP if vol <= limit)
RETURN f"https://basket-{basket:02d}.wbbasket.ru/vol{vol}/part{part}/{nm}/images/big/1.jpg"
```
