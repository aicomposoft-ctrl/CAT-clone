# PRD — Content Scoring: Image (CLIP)

**Feature ID:** content-scoring-image
**Sprint:** 3
**Priority:** P0
**Story Points:** 13

---

## Problem Statement

Collector сервис уже собирает изображения товарных карточек и сохраняет их в MinIO (`collected_image_url` в `content_scores`). Эталонные изображения брендов загружаются через Reference Upload API и хранятся в MinIO. Но никакого автоматического сравнения не происходит — поле `image_score` в `content_scores` всегда NULL. Бренды не знают, насколько реальное изображение на маркетплейсе соответствует их эталону.

## Solution

ML-pipeline в сервисе `processor/`, которая:
1. При загрузке reference-изображения — вычисляет CLIP-эмбеддинг и кеширует в Redis
2. Ежедневно в 06:00 UTC — вычисляет cosine similarity между эталонным и собранным изображением, пишет `image_score` в `content_scores`

## Users & Value

| Persona | Gain |
|---------|------|
| Бренд-менеджер | Видит ежедневно: "на Wildberries изображение соответствует эталону на 87%, на Ozon — 43%" |
| Digital commerce агентство | Автоматическое выявление деградации контента без ручного просмотра |
| CAT платформа | Заполняется первый компонент `content_total` (40% веса) |

## Scope (MVP)

### In scope
- `compute_clip_embedding` Celery task: эмбеддинг reference-image → Redis
- `score_image_content_all` Celery task: ежедневный batch-скоринг
- `score_image_content` per-row task: cosine sim → UPDATE `content_scores.image_score`
- Processor сервис: FastAPI app skeleton + Celery worker + Beat schedule
- Модель: `openai/clip-vit-base-patch32` через HuggingFace transformers
- Мультитенантная изоляция: org_id через join chain

### Out of scope (Sprint 3, отдельная фича)
- Text scoring (multilingual-e5) — `content-scoring-text`
- `content_total` aggregation — зависит от text scoring
- GPU inference (CPU-only для MVP)
- Batch CLIP inference с GPU autoscaling

## Success Metrics

| Metric | Target |
|--------|--------|
| `image_score` заполнен к 08:00 UTC | ≥ 99% строк за сегодня |
| Latency на 1000 SKU | ≤ 10 мин (CPU) |
| Reference embedding cache hit rate | ≥ 95% |
| Cross-tenant data leakage | 0 инцидентов |
