"""Tenant authentication: resolve a JWT into a TenantContext.

Every request must carry a bearer token whose ``tenant_id`` claim scopes all
downstream DB access. There is no "global" query path — tenant isolation is
enforced at the edge and threaded through the request.
"""
from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import Depends, Header, HTTPException, status

from app.config import Settings, get_settings


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    user_id: str


def _decode(token: str, settings: Settings) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:  # noqa: BLE001 - normalize all JWT errors to 401
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        ) from exc


def get_tenant_context(
    authorization: str = Header(default=""),
    settings: Settings = Depends(get_settings),
) -> TenantContext:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token"
        )
    payload = _decode(authorization.split(" ", 1)[1], settings)
    tenant_id = payload.get("tenant_id")
    user_id = payload.get("sub", "unknown")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing tenant_id claim"
        )
    return TenantContext(tenant_id=tenant_id, user_id=user_id)


def issue_token(*, tenant_id: str, user_id: str, settings: Settings | None = None) -> str:
    """Helper for tests / local dev to mint a tenant-scoped token."""
    settings = settings or get_settings()
    return jwt.encode(
        {"tenant_id": tenant_id, "sub": user_id},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
