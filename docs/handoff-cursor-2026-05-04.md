# Handoff: CAT → Cursor — 2026-05-04

## Контекст проекта

CAT (Commerce Analytics Tool) — локальный MVP для мониторинга онлайн-полки FMCG-брендов.
Запускается через `docker compose up` на домашнем ПК (домашний IP, не датацентровый).
Единственная активная площадка на данный момент: **Magnit (magnit.ru)**.

---

## Что было сделано (последняя сессия Claude, 2026-05-04)

### 1. Исправлен ContentDrillDrawer (модалка сравнения)

**Файл:** `services/frontend/src/pages/Content/components/ContentDrillDrawer.tsx`

- Скоры теперь отображаются корректно (0-100%, не 0-1%). Нормализация перенесена в API (`services/api/app/content/service.py` — функция `_pct()`).
- Добавлен раздел **"Состав (diff)"** — ранее отсутствовал.
- Добавлена секция **"Изображение"** с сравнением эталон vs собранное.
- Собранное фото: использует `collectedStorageKeyToImageSrc()` из `api/catalog.ts` (bucket `cat-data`).
- Эталонное фото: `referenceStorageKeyToImageSrc()` (bucket `cat-references`).
- Добавлен `Tooltip` с объяснением метода CLIP на иконке ⓘ рядом со строкой "Изображение".

### 2. Исправлен diff-алгоритм текста

**Файл:** `services/frontend/src/pages/Content/components/ContentDrillDrawer.tsx`

Функция `renderDiff`:
- `preprocessText()` — мержит переносы слов ("про- дукт" → "продукт"), нормализует пробелы
- `normalizeWord()` — убирает пунктуацию (`«».,;:!?—–-`), lowercase, trim
- Слова сравниваются по нормализованным формам → "«печенье»," == "«печенье»"

### 3. Исправлена нормализация скоров на Dashboard

**Файл:** `services/api/app/dashboard/router.py`

- `avg_content_score` и `content_total` в red_zone умножаются на 100 (были "0.9%" вместо "90%")

### 4. Добавлена функция `collectedStorageKeyToImageSrc`

**Файл:** `services/frontend/src/api/catalog.ts`

```typescript
const MINIO_BUCKET_DATA = 'cat-data'

export function collectedStorageKeyToImageSrc(stored: string | null): string | null {
  if (!stored) return null
  if (/^https?:\/\//i.test(stored)) return rewriteMinioUrl(stored)
  const key = stored.replace(/^\/+/, '')
  if (key.startsWith(`${MINIO_BUCKET_DATA}/`)) return `/s3/${key}`
  return `/s3/${MINIO_BUCKET_DATA}/${key}`
}
```

### 5. Magnit scraper — парсинг состава

**Файл:** `services/collector/app/scrapers/magnit.py`

Добавлена функция `_extract_composition_from_nuxt(html)`:
- Находит состав в SSR Nuxt payload (самый большой `<script>` тег, ~206KB)
- Regex: `"Состав",[],\"stringType\",\"(.*?)\"`
- Очищает `\n` переносы и дефис-переносы

---

## Что НЕ работает / требует доработки

### ПРИОРИТЕТ 1: Отзывы Magnit — не работает

**Проблема:** `collect_reviews()` перебирает 4 URL-кандидата, все возвращают 301 (redirect) или 404. Правильный endpoint неизвестен.

**Что нужно сделать:**
1. Открыть Chrome → DevTools → Network
2. Зайти на страницу товара Магнит, например: `https://magnit.ru/product/PRODUCT_ID`
3. Отфильтровать запросы по `review`
4. Скопировать точный URL из DevTools (включая query params и заголовки `x-app-version`, `x-device-id` и др.)
5. Обновить `candidate_urls` в `collect_reviews()` и добавить нужные заголовки

**Файл:** `services/collector/app/scrapers/magnit.py`, метод `collect_reviews()` (~строка 222)

Текущие кандидаты (все провалились):
```
https://magnit.ru/api/v2/catalog/product/{id}/reviews/
https://magnit.ru/api/v1/catalog/product/{id}/reviews/
https://magnit.ru/api/v1/catalog/products/{id}/reviews/
https://magnit.ru/api/v1/product/{id}/reviews/
```

Вероятные причины: нужны `x-app-version` header, CSRF-токен из cookie сессии, или reviews живут на отдельном поддомене.

---

### ПРИОРИТЕТ 2: Добавить вторую площадку для MVP

Из research-сессии (2026-04-20): **ВкусВилл** (vkusvill.ru) имеет открытый REST JSON API без блокировок датацентровых IP.

**API ВкусВилла:**
- Product detail: `GET https://vkusvill.ru/api/v4/products/{slug}/`
- Responses: JSON, без авторизации, CORS открытый
- Rate limit: ~1 req/sec безопасно

Нужно реализовать `VkusvillScraper` по образцу `MagnitScraper`.

---

### ПРИОРИТЕТ 3: OCR для сравнения фотографий (Featurelist)

**Контекст:** CLIP (ViT) не читает текст на упаковке как OCR — он анализирует визуальную семантику. Это значит что два похожих продукта с разными надписями получат высокий скор (~0.89).

**Задача:** Добавить OCR-компоненту в content scoring pipeline:
- Библиотека: `pytesseract` (Python) или `easyocr` (лучше для русского языка)
- OCR текст с упаковки → fuzzy match с эталонным текстом → `ocr_score`
- Добавить `ocr_score` в `content_scores` таблицу и в scoring formula
- Отображать в UI как отдельную строку в Descriptions

---

## Архитектура image scoring (важно понять)

```
Загрузка эталона (UI)
  → POST /skus/{id}/reference/image
  → сохраняется в MinIO bucket: cat-references
  → автоматически триггерит: celery task cat.compute_clip_embedding --queue ml
  → CLIP embedding сохраняется в Redis

Сбор данных (Celery collector)
  → MagnitScraper.collect_content()
  → изображение скачивается → MinIO bucket: cat-data
  → celery task processor.score_image_content --queue ml
  → CLIP embedding для collected image + cosine_sim с reference embedding из Redis
  → результат → content_scores таблица
```

**Ручной пересчёт скора (если поменяли эталон):**
```bash
# 1. Пересчитать reference embedding
docker exec cat-clone-processor-1 celery -A app.celery_app call cat.compute_clip_embedding \
  --args '["<sku_id>"]' --queue ml

# 2. Пересчитать image score
docker exec cat-clone-processor-1 celery -A app.celery_app call processor.score_image_content \
  --args '["<content_score_id>","<sku_id>","<s3_key_of_collected_image>"]' --queue ml
```

---

## Переменные для тестового товара (Магнит)

```
SKU name:     Фруктовое пюре Яблоко-банан-печенье 90г  
sku_id:       ad1eff66-e6be-4498-8214-29321e892ad6
sku_platform: 1106c607-64d8-4a25-a8b1-a5d49cec2ae8
org_id:       e741f8e5-ca5b-4d2c-99b7-b5ee310b8194
product_id:   (Magnit numeric ID — см. sku_platforms.external_id в DB)
```

---

## Инфраструктура (локально)

| Сервис | URL | Назначение |
|--------|-----|-----------|
| Frontend | http://localhost:3000 | React UI |
| API | http://localhost:8000 | FastAPI |
| Flower | http://localhost:5555 | Celery monitoring |
| MinIO | http://localhost:9001 | S3 console |
| MailHog | http://localhost:8025 | Email preview |

**Важно:** Изменения Python-кода требуют `docker compose up --build <service> -d`.
Два collector контейнера: `cat-clone-collector-1` и `cat-clone-collector-playwright-1`.
Processor (`ml` queue): `cat-clone-processor-1`.

---

## Bucket policies MinIO (должны быть public read)

```bash
# Проверить что оба бакета открыты для proxy:
python3 -c "
import boto3
s3 = boto3.client('s3', endpoint_url='http://localhost:9000',
  aws_access_key_id='minioadmin', aws_secret_access_key='minioadmin')
import json
policy = {'Version':'2012-10-17','Statement':[{'Effect':'Allow','Principal':'*',
  'Action':'s3:GetObject','Resource':'arn:aws:s3:::BUCKET/*'}]}
for b in ['cat-references','cat-data']:
    p = dict(policy); p['Statement'][0]['Resource'] = f'arn:aws:s3:::{b}/*'
    s3.put_bucket_policy(Bucket=b, Policy=json.dumps(p))
    print(f'{b}: public read OK')
"
```
