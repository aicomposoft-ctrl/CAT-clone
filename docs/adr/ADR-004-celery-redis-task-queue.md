# ADR-004: Celery + Redis для асинхронных задач

**Дата:** 2026-03-01  
**Статус:** Accepted  
**Авторы:** CAT Team

---

## Контекст

Скрапинг 110+ платформ занимает часы. ML-инференс (CLIP, ruBERT) CPU/GPU-интенсивен. Эти процессы нельзя выполнять в HTTP-запросе. Нужна очередь задач с планировщиком (ночной сбор данных).

## Рассматриваемые варианты

| Вариант | Плюсы | Минусы |
|---------|-------|--------|
| **Celery + Redis (выбран)** | Python-native, Beat для cron, Flower для мониторинга | Redis не персистентен по умолчанию |
| Celery + RabbitMQ | Надёжнее очередь | Ещё один сервис, сложнее |
| RQ (Redis Queue) | Проще Celery | Нет Beat, слабый мониторинг |
| Dramatiq | Быстрее Celery | Меньше экосистема |
| FastAPI BackgroundTasks | Встроен | Нет retry, нет распределённости |

## Решение

**Celery 5.x** с брокером **Redis 7** и бэкендом результатов Redis.

- `collector/tasks.py` — задачи скрапинга (per-platform, per-sku)
- `processor/tasks.py` — ML-задачи (content scoring, sentiment)
- `beat` — отдельный контейнер с Celery Beat (строго 1 реплика)
- `flower` — мониторинг задач на порту 5555

```python
# Планировщик: ночной запуск в 2:00 UTC
CELERYBEAT_SCHEDULE = {
    'nightly-scrape': {
        'task': 'collector.tasks.run_full_scrape',
        'schedule': crontab(hour=2, minute=0),
    }
}
```

## Последствия

- **Положительные:** retry с exponential backoff, приоритизация очередей, горизонтальный скейл воркеров
- **Отрицательные:** Beat должен иметь ровно 1 реплику (иначе дублирование задач)
- **Правило:** Redis настроен с `appendonly yes` для персистентности очереди при рестарте
