# PRD — Content Scoring: Text (multilingual-e5)

**Feature ID:** content-scoring-text
**Sprint:** 3
**Priority:** P0
**Story Points:** 8

---

## Problem Statement

`content_scores.image_score` уже заполняется (Sprint 3a). Но `description_score`, `composition_score` и `content_total` остаются NULL — бренд видит только треть картины качества контента. Без текстового скоринга невозможно ответить на ключевой вопрос: "Правильно ли описан мой товар на маркетплейсах?"

## Solution

Ежедневная Celery-задача в `processor/` вычисляет cosine similarity между:
- `ref_emb:{sku_id}:desc` (эталонное описание, 768-dim) и `collected_description`
- `ref_emb:{sku_id}:comp` (эталонный состав, 768-dim) и `collected_composition`

После записи обоих значений вычисляется `content_total` по формуле бизнес-весов.

## Formula

```
content_total = 0.40 × image_score + 0.35 × description_score + 0.25 × composition_score
```

`content_total` вычисляется только если все три компонента не NULL.

## Users & Value

| Persona | Gain |
|---------|------|
| Бренд-менеджер | "На Wildberries описание соответствует эталону на 91%, состав — на 78%" |
| CAT платформа | Первый полный `content_total` — единая метрика качества карточки |

## Scope (MVP)

### In scope
- `score_text_content_all` — оркестратор (06:30 UTC)
- `score_text_content` — per-row: description_score + composition_score + content_total
- E5 encoder singleton (768-dim, `intfloat/multilingual-e5-base`)
- `content_total` = только если `image_score IS NOT NULL`
- Регистрация Beat schedule в `celery_app.py`

### Out of scope
- `compute_text_embedding` task — уже реализована в `services/api/app/tasks/embedding_tasks.py`
- Пересчёт `content_total` при изменении весов (v2.0)
- GPU inference

## Success Metrics

| Metric | Target |
|--------|--------|
| `description_score` заполнен к 08:00 UTC | ≥ 99% строк за сегодня |
| `content_total` заполнен при наличии всех 3 компонент | 100% |
| Latency на 1000 SKU | ≤ 5 мин (текст без MinIO, только БД + Redis) |
