"""Celery app for async / long-running agent work (batch document processing,
scheduled ERP syncs, etc.). Broker + backend are Redis by default."""
from __future__ import annotations

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "agent_platform",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["workers.tasks"],
)
celery_app.conf.update(task_track_started=True, task_time_limit=600)
