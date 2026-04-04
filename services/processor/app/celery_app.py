"""
Celery application for the CAT processor service.

Registers two groups of tasks:
  1. ML embedding tasks (same names as the API dispatches):
       cat.compute_clip_embedding  — reference image → CLIP → Redis
  2. Daily scoring tasks:
       processor.score_image_content_all  — orchestrator (Beat 06:00 UTC)
       processor.score_image_content      — per-row CLIP cosine scoring

Beat schedule:
  06:00 UTC — score_image_content_all
  06:30 UTC — reserved for text scoring (Sprint 3b, not yet registered)

Worker pool:
  prefork ONLY. asyncio.run() calls inside tasks are incompatible with
  gevent/eventlet. Set --pool=prefork explicitly (default on Linux).
"""

from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery(
    "cat_processor",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "app.tasks.clip_embedding_task",
        "app.tasks.image_scoring_task",
        "app.tasks.text_scoring_task",
        "app.tasks.sentiment_task",
    ],
)

celery_app.conf.beat_schedule = {
    "score-image-content-daily": {
        "task": "processor.score_image_content_all",
        "schedule": crontab(hour=6, minute=0),   # 06:00 UTC — after collector finishes
    },
    "score-text-content-daily": {
        "task": "processor.score_text_content_all",
        "schedule": crontab(hour=6, minute=30),  # 06:30 UTC — after image scoring
    },
    "score-pending-reviews-daily": {
        "task": "processor.score_pending_reviews",
        "schedule": crontab(hour=3, minute=0),   # 03:00 UTC — after collect_reviews (02:00)
    },
}

celery_app.conf.timezone = "UTC"
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]
