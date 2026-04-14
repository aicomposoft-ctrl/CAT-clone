# Celery entrypoint — re-exports celery_app so `celery -A tasks` works
from app.celery_app import celery_app  # noqa: F401
