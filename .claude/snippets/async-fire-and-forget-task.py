"""
Async Fire-and-Forget with Exception Isolation
===============================================

Pattern: asyncio.create_task() wrapped in try/except for non-critical
background operations that must not block or fail the main response.

When to use:
  - Updating non-critical metadata (last_used_at, last_seen, access_count)
  - Sending analytics events that shouldn't affect user-facing latency
  - Triggering background processing after returning a response

When NOT to use:
  - Critical operations (payment processing, order creation, auth state changes)
  - Operations that must be retried on failure (use Celery/task queues instead)
  - When you need to know if the operation succeeded (fire-and-forget means you don't)

Prerequisites: Python asyncio (stdlib), FastAPI or any async framework

Warning: Tasks launched with create_task() die if the event loop closes before
they complete. For truly reliable background work, use a task queue (Celery, RQ).

Maturity: 🔴 Alpha
Source: CAT (core/deps.py — API key last_used_at update), 2026-04-05
"""

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger(__name__)


def fire_and_forget(coro: Coroutine, *, context: str = "fire_and_forget") -> None:
    """
    Schedule a coroutine as a background task without awaiting it.

    Exceptions inside the coroutine are logged as WARNING and never propagated.
    The current request continues immediately.

    Args:
        coro:    The coroutine to run in the background.
        context: Label for log lines (helps identify which task failed).

    Example:
        fire_and_forget(
            update_last_used(db, key.id),
            context="api_key.last_used"
        )
    """
    try:
        task = asyncio.create_task(coro)
        task.add_done_callback(
            lambda t: _log_exception(t, context=context)
        )
    except Exception as exc:
        # create_task itself can fail if the event loop is closing
        logger.warning("%s: create_task failed: %s", context, exc)


def _log_exception(task: asyncio.Task, *, context: str) -> None:
    """Callback: log exception from a finished task without re-raising."""
    if not task.cancelled() and (exc := task.exception()):
        logger.warning("%s: background task failed: %s", context, exc)


# --- Simpler inline variant (when you don't want the helper) ---

async def example_route_handler(item_id: str, db) -> dict:
    """Example: update last_used_at without blocking the response."""
    item = await ItemRepository.get(db, item_id)

    # Non-critical update — don't block the response, don't crash if it fails
    try:
        asyncio.create_task(
            ItemRepository.update_last_used(db, item_id)
        )
    except Exception as exc:
        logger.warning("last_used update failed for %s: %s", item_id, exc)

    return {"id": item_id, "name": item.name}
