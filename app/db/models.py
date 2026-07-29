"""Multi-tenant data model for the document-intelligence + ERP agent.

Every business row carries a ``tenant_id``. A :class:`Document` moves through
OCR -> extraction -> validation -> (ERP push | exception queue). Extracted data
and validation issues are stored as JSON so the record is self-describing. The
:class:`AuditLog` table is the EU AI Act / GDPR trail (extract + validate
outcomes), unchanged in spirit from the foundation.
"""
from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DocumentStatus(str, enum.Enum):
    RECEIVED = "received"
    EXTRACTED = "extracted"
    VALIDATED = "validated"          # passed validation, en route to ERP
    PUSHED_TO_ERP = "pushed_to_erp"  # clean record written downstream
    EXCEPTION = "exception"          # failed validation -> human queue
    FAILED = "failed"                # transient error (e.g. ERP unreachable)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)

    # Dedupe key: a content hash so re-uploading the same document is idempotent.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)

    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus), default=DocumentStatus.RECEIVED, nullable=False
    )
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # InvoiceData
    issues: Mapped[list | None] = mapped_column(JSON, nullable=True)      # [ValidationIssue]
    extracted_by: Mapped[str | None] = mapped_column(String(16), nullable=True)  # "llm"|"code"
    erp_record_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    __table_args__ = (
        Index("ix_documents_tenant_status", "tenant_id", "status"),
        # Re-uploading identical content is a safe no-op, not a duplicate row.
        UniqueConstraint("tenant_id", "content_hash", name="uq_documents_tenant_hash"),
    )


class AuditLog(Base):
    """Immutable-by-convention record of an extract/validate/push decision."""

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    decided_by: Mapped[str] = mapped_column(String(16), nullable=False)  # "llm" | "code"
    output: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (Index("ix_audit_logs_tenant_created", "tenant_id", "created_at"),)
