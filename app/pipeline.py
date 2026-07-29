"""Document-processing pipeline: OCR -> extract -> validate -> ERP | exception.

Callable inline (from the API) or from a Celery task with identical behavior.
Idempotent and re-validating: it re-reads the document and only acts when the
document is in a non-terminal state, so a retried task/upload is a safe no-op.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents.extraction_graph import build_extraction_graph
from app.db.models import AuditLog, Document, DocumentStatus
from app.erp.adapter import ERPAdapter, ERPError
from app.extraction.extractor import Extractor
from app.observability.logging import get_logger
from app.schemas import InvoiceData

log = get_logger("pipeline")

# Fully-processed states; reprocessing them would be wrong.
_TERMINAL = {DocumentStatus.PUSHED_TO_ERP, DocumentStatus.EXCEPTION}


def process_document(
    db: Session,
    *,
    document_id: str,
    tenant_id: str,
    extractor: Extractor,
    erp: ERPAdapter,
    tolerance: float,
) -> None:
    doc = db.get(Document, document_id)
    if doc is None or doc.tenant_id != tenant_id:
        log.warning("pipeline.doc_missing", document_id=document_id, tenant_id=tenant_id)
        return
    if doc.status in _TERMINAL:
        log.info("pipeline.skip_terminal", document_id=document_id, status=doc.status.value)
        return

    # Resume: if already VALIDATED (extraction+validation done, ERP push pending
    # or failed), skip straight to the ERP push without re-extracting.
    if doc.status not in (DocumentStatus.VALIDATED, DocumentStatus.FAILED):
        graph = build_extraction_graph(extractor)
        final = graph.invoke({"raw_text": doc.raw_text or "", "tolerance": tolerance})
        invoice: InvoiceData = final["invoice"]
        issues = final["issues"]

        doc.extracted = invoice.model_dump()
        doc.extracted_by = final["extracted_by"]
        doc.issues = [i.model_dump() for i in issues]
        db.add(AuditLog(tenant_id=tenant_id, document_id=doc.id, actor="extraction-agent",
                        action="doc.extract", decided_by=final["extracted_by"],
                        output=f"vendor={invoice.vendor_name!r} total={invoice.total}"))

        if issues:
            doc.status = DocumentStatus.EXCEPTION
            db.add(AuditLog(tenant_id=tenant_id, document_id=doc.id, actor="validator",
                            action="doc.validate", decided_by="code",
                            output=f"{len(issues)} issue(s): "
                                   + ", ".join(i.code for i in issues)))
            db.commit()
            return

        doc.status = DocumentStatus.VALIDATED
        db.add(AuditLog(tenant_id=tenant_id, document_id=doc.id, actor="validator",
                        action="doc.validate", decided_by="code", output="valid"))
        db.commit()

    # Guard: if a prior attempt already got an ERP id back, don't re-post on
    # resume — just finalize the status. (Belt-and-suspenders alongside the
    # adapter's business-key idempotency.)
    if doc.erp_record_id:
        doc.status = DocumentStatus.PUSHED_TO_ERP
        db.commit()
        return

    # Push the validated invoice to the ERP. Failure is recoverable.
    invoice = InvoiceData(**doc.extracted)
    try:
        doc.erp_record_id = erp.post_invoice(invoice)
    except ERPError as exc:
        doc.status = DocumentStatus.FAILED
        db.add(AuditLog(tenant_id=tenant_id, document_id=doc.id, actor="erp-adapter",
                        action="erp.push_failed", decided_by="code", output=str(exc)))
        db.commit()
        raise

    doc.status = DocumentStatus.PUSHED_TO_ERP
    db.add(AuditLog(tenant_id=tenant_id, document_id=doc.id, actor="erp-adapter",
                    action="erp.pushed", decided_by="code", output=f"erp_id={doc.erp_record_id}"))
    db.commit()
