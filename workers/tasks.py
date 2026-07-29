"""Async tasks. The pipeline lives in app/; the worker just runs it off the
request path. Retry-safe: the pipeline re-reads the document and no-ops if it's
already terminal, so a redelivered message never double-processes."""
from __future__ import annotations

from app.config import get_settings
from app.db.base import SessionLocal
from app.pipeline import process_document
from app.runtime import get_erp, get_extractor_singleton
from workers.celery_app import celery_app


@celery_app.task(name="workers.ping")
def ping() -> str:
    """Trivial task to verify broker connectivity in CI / smoke tests."""
    return "pong"


@celery_app.task(
    name="workers.process_document",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,  # redeliver on crash; pipeline is idempotent so it's safe
)
def process_document_task(self, *, document_id: str, tenant_id: str) -> str:
    db = SessionLocal()
    try:
        process_document(
            db, document_id=document_id, tenant_id=tenant_id,
            extractor=get_extractor_singleton(), erp=get_erp(),
            tolerance=get_settings().amount_tolerance,
        )
        return "ok"
    except Exception as exc:  # noqa: BLE001 - ERP/network failures are retryable
        raise self.retry(exc=exc) from exc
    finally:
        db.close()
