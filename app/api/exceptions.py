"""Human exception queue: documents that failed deterministic validation, with
the specific failing fields, plus a correct-and-reprocess action."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.documents import to_document_out
from app.auth.tenant import TenantContext, get_tenant_context
from app.config import get_settings
from app.db.base import get_db
from app.db.models import AuditLog, Document, DocumentStatus
from app.pipeline import process_document
from app.runtime import get_erp, get_extractor_singleton
from app.schemas import DocumentOut, InvoiceData
from app.validation.validator import validate_invoice

router = APIRouter(prefix="/exceptions", tags=["exceptions"])


# Both states need a human: EXCEPTION failed validation; FAILED failed the ERP
# push (e.g. transient outage) and would otherwise be invisible.
_NEEDS_HUMAN = (DocumentStatus.EXCEPTION, DocumentStatus.FAILED)


@router.get("", response_model=list[DocumentOut])
def list_exceptions(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> list[DocumentOut]:
    rows = db.scalars(
        select(Document).where(
            Document.tenant_id == ctx.tenant_id,
            Document.status.in_(_NEEDS_HUMAN),
        ).order_by(Document.created_at.desc())
    ).all()
    return [to_document_out(d) for d in rows]


@router.post("/{document_id}/resolve", response_model=DocumentOut)
def resolve_exception(
    document_id: str,
    corrected: InvoiceData,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> DocumentOut:
    """A human supplies corrected fields; the correction is re-validated by the
    SAME deterministic rules and, if now valid, pushed to the ERP. The human
    fixes data — they do NOT bypass validation, and the correction is NOT
    re-extracted from the raw text (that would discard their edits)."""
    doc = db.get(Document, document_id)
    if doc is None or doc.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.status not in _NEEDS_HUMAN:
        raise HTTPException(status_code=409, detail="Document is not awaiting a human")

    tolerance = get_settings().amount_tolerance
    issues = validate_invoice(corrected, tolerance=tolerance)
    doc.extracted = corrected.model_dump()
    doc.extracted_by = "human"
    doc.issues = [i.model_dump() for i in issues]
    db.add(AuditLog(tenant_id=ctx.tenant_id, document_id=doc.id, actor=ctx.user_id,
                    action="exception.resolve", decided_by="code",
                    output=f"human correction re-validated: {len(issues)} issue(s)"))

    if issues:
        # Still invalid — stays in the queue with the remaining issues.
        doc.status = DocumentStatus.EXCEPTION
        db.commit()
        db.refresh(doc)
        return to_document_out(doc)

    # Now valid: mark VALIDATED and let the pipeline push to ERP (it skips
    # extraction for a VALIDATED doc, so the human's data is preserved).
    doc.status = DocumentStatus.VALIDATED
    db.commit()
    process_document(
        db, document_id=doc.id, tenant_id=ctx.tenant_id,
        extractor=get_extractor_singleton(), erp=get_erp(), tolerance=tolerance,
    )
    db.refresh(doc)
    return to_document_out(doc)
