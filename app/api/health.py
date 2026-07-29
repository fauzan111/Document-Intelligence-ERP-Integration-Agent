"""Liveness / readiness endpoints for containers and load balancers."""
from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    s = get_settings()
    return {"status": "ok", "app": s.app_name, "environment": s.environment}
