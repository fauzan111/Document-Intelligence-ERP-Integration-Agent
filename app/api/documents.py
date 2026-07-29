"""Document ingestion + processing API. Idempotent on content hash."""
from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.tenant import TenantContext, get_tenant_context
from app.config import get_settings
from app.db.base import get_db
from app.db.models import Document, DocumentStatus
from app.ocr.ocr import OCRError, decode_pdf_base64
from app.pipeline import process_document
from app.runtime import get_erp, get_extractor_singleton, get_ocr
from app.schemas import DocumentOut, DocumentUploadIn, InvoiceData, ValidationIssue

router = APIRouter(prefix="/documents", tags=["documents"])

_TERMINAL = {DocumentStatus.PUSHED_TO_ERP, DocumentStatus.EXCEPTION}


def to_document_out(doc: Document) -> DocumentOut:
    return DocumentOut(
        id=doc.id, filename=doc.filename, status=doc.status.value,
        extracted=InvoiceData(**doc.extracted) if doc.extracted else None,
        issues=[ValidationIssue(**i) for i in (doc.issues or [])],
        erp_record_id=doc.erp_record_id, extracted_by=doc.extracted_by,
    )


@router.post("", response_model=DocumentOut)
def upload_document(
    body: DocumentUploadIn,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> DocumentOut:
    # 1. OCR / text extraction up front (also gives us the content to hash).
    try:
        pdf_bytes = decode_pdf_base64(body.pdf_base64)
        raw_text = get_ocr().extract_text(text=body.text, pdf_bytes=pdf_bytes)
    except OCRError as exc:
        raise HTTPException(status_code=422, detail=f"OCR failed: {exc}") from exc

    content_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

    # 2. Idempotency: same content for this tenant -> return the existing doc.
    existing = db.scalar(
        select(Document).where(
            Document.tenant_id == ctx.tenant_id, Document.content_hash == content_hash
        )
    )
    if existing is not None:
        if existing.status not in _TERMINAL:  # resume unfinished work
            _run(db, existing.id, ctx.tenant_id)
            db.refresh(existing)
        return to_document_out(existing)

    # 3. Create + process. The unique constraint arbitrates concurrent dupes.
    doc = Document(tenant_id=ctx.tenant_id, content_hash=content_hash,
                   filename=body.filename, raw_text=raw_text, status=DocumentStatus.RECEIVED)
    db.add(doc)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        winner = db.scalar(
            select(Document).where(
                Document.tenant_id == ctx.tenant_id, Document.content_hash == content_hash
            )
        )
        if winner is not None:
            return to_document_out(winner)
        raise

    _run(db, doc.id, ctx.tenant_id)
    db.refresh(doc)
    return to_document_out(doc)


def _run(db: Session, document_id: str, tenant_id: str) -> None:
    process_document(
        db, document_id=document_id, tenant_id=tenant_id,
        extractor=get_extractor_singleton(), erp=get_erp(),
        tolerance=get_settings().amount_tolerance,
    )


@router.get("", response_model=list[DocumentOut])
def list_documents(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> list[DocumentOut]:
    rows = db.scalars(
        select(Document).where(Document.tenant_id == ctx.tenant_id)
        .order_by(Document.created_at.desc())
    ).all()
    return [to_document_out(d) for d in rows]


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> DocumentOut:
    doc = db.get(Document, document_id)
    if doc is None or doc.tenant_id != ctx.tenant_id:  # tenant scoping
        raise HTTPException(status_code=404, detail="Document not found")
    return to_document_out(doc)
