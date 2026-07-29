"""Pipeline resume safety: a VALIDATED document that already has an ERP id must
not be pushed again (no double-post on retry)."""
from __future__ import annotations

import uuid

from app.db.base import SessionLocal
from app.db.models import Document, DocumentStatus, Tenant
from app.erp.adapter import ERPAdapter
from app.extraction.extractor import RegexExtractor
from app.pipeline import process_document
from app.sample_invoices import VALID_INVOICE


class _CountingERP(ERPAdapter):
    def __init__(self) -> None:
        self.calls = 0

    def post_invoice(self, inv):  # noqa: ARG002
        self.calls += 1
        return "SAP-SHOULD-NOT-HAPPEN"


def test_validated_doc_with_erp_id_is_not_reposted():
    db = SessionLocal()
    try:
        tenant = Tenant(name=f"t-{uuid.uuid4()}")
        db.add(tenant)
        db.flush()
        inv = RegexExtractor().extract(VALID_INVOICE)
        doc = Document(
            tenant_id=tenant.id, content_hash=uuid.uuid4().hex, filename="v.txt",
            status=DocumentStatus.VALIDATED, raw_text=VALID_INVOICE,
            extracted=inv.model_dump(), erp_record_id="SAP-ALREADY-PUSHED",
        )
        db.add(doc)
        db.commit()

        erp = _CountingERP()
        process_document(db, document_id=doc.id, tenant_id=tenant.id,
                         extractor=RegexExtractor(), erp=erp, tolerance=0.02)

        refreshed = db.get(Document, doc.id)
        assert refreshed.status == DocumentStatus.PUSHED_TO_ERP
        assert refreshed.erp_record_id == "SAP-ALREADY-PUSHED"  # unchanged
        assert erp.calls == 0  # guard prevented a second POST
    finally:
        db.close()
