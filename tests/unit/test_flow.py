"""End-to-end document flow through the API: upload -> extract -> validate ->
ERP push or exception queue -> human resolve."""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.db.base import SessionLocal
from app.db.models import Document, DocumentStatus
from app.main import app
from app.sample_invoices import BAD_TOTALS_INVOICE, BAD_VAT_INVOICE, VALID_INVOICE


def _signup(client: TestClient) -> dict:
    r = client.post("/tenants/signup", json={"name": f"mfg-{uuid.uuid4()}"}).json()
    return {"Authorization": f"Bearer {r['access_token']}"}


def test_valid_invoice_pushed_to_erp():
    with TestClient(app) as client:
        auth = _signup(client)
        out = client.post("/documents", headers=auth,
                          json={"filename": "inv.txt", "text": VALID_INVOICE}).json()
        assert out["status"] == "pushed_to_erp"
        assert out["erp_record_id"] and out["erp_record_id"].startswith("SAP-")
        assert out["issues"] == []
        assert out["extracted"]["vendor_vat_id"] == "IT07643520567"


def test_bad_totals_routed_to_exception_queue():
    with TestClient(app) as client:
        auth = _signup(client)
        out = client.post("/documents", headers=auth,
                          json={"filename": "bad.txt", "text": BAD_TOTALS_INVOICE}).json()
        assert out["status"] == "exception"
        assert out["erp_record_id"] is None
        assert any(i["code"] == "totals_mismatch" for i in out["issues"])

        # It shows up in the exception queue.
        q = client.get("/exceptions", headers=auth).json()
        assert any(d["id"] == out["id"] for d in q)


def test_bad_vat_routed_to_exception_queue():
    with TestClient(app) as client:
        auth = _signup(client)
        out = client.post("/documents", headers=auth,
                          json={"filename": "badvat.txt", "text": BAD_VAT_INVOICE}).json()
        assert out["status"] == "exception"
        assert any(i["code"] == "vat_checksum" for i in out["issues"])


def test_duplicate_upload_is_idempotent():
    with TestClient(app) as client:
        auth = _signup(client)
        first = client.post("/documents", headers=auth,
                            json={"filename": "a.txt", "text": VALID_INVOICE}).json()
        second = client.post("/documents", headers=auth,
                             json={"filename": "a.txt", "text": VALID_INVOICE}).json()
        assert first["id"] == second["id"]  # same content hash -> same document
        docs = client.get("/documents", headers=auth).json()
        assert len(docs) == 1


def test_human_resolves_exception_then_pushed():
    with TestClient(app) as client:
        auth = _signup(client)
        out = client.post("/documents", headers=auth,
                          json={"filename": "bad.txt", "text": BAD_TOTALS_INVOICE}).json()
        assert out["status"] == "exception"

        # Human corrects the total so subtotal+vat==total, re-validated by code.
        corrected = out["extracted"]
        corrected["total"] = 122.0  # 100 + 22
        resolved = client.post(f"/exceptions/{out['id']}/resolve", headers=auth,
                               json=corrected).json()
        assert resolved["status"] == "pushed_to_erp"
        assert resolved["extracted_by"] == "human"
        assert resolved["erp_record_id"]


def test_failed_document_is_listable_and_resolvable():
    """A doc stranded in FAILED (e.g. transient ERP outage) must stay visible in
    the human queue and be resolvable — not silently disappear."""
    with TestClient(app) as client:
        auth = _signup(client)
        out = client.post("/documents", headers=auth,
                          json={"filename": "v.txt", "text": VALID_INVOICE}).json()
        doc_id = out["id"]

        # Simulate the aftermath of an ERP outage: flip to FAILED, clear erp id.
        db = SessionLocal()
        try:
            d = db.get(Document, doc_id)
            d.status = DocumentStatus.FAILED
            d.erp_record_id = None
            db.commit()
        finally:
            db.close()

        # It appears in the queue...
        queue = client.get("/exceptions", headers=auth).json()
        assert any(x["id"] == doc_id for x in queue)

        # ...and re-submitting the (already valid) data pushes it through.
        corrected = out["extracted"]
        resolved = client.post(f"/exceptions/{doc_id}/resolve", headers=auth,
                               json=corrected).json()
        assert resolved["status"] == "pushed_to_erp"
        assert resolved["erp_record_id"]


def test_resolve_with_still_invalid_data_stays_in_queue():
    with TestClient(app) as client:
        auth = _signup(client)
        out = client.post("/documents", headers=auth,
                          json={"filename": "bad.txt", "text": BAD_TOTALS_INVOICE}).json()
        # "Correction" that is still wrong -> remains an exception.
        corrected = out["extracted"]
        corrected["total"] = 9999.0
        resolved = client.post(f"/exceptions/{out['id']}/resolve", headers=auth,
                               json=corrected).json()
        assert resolved["status"] == "exception"
        assert any(i["code"] == "totals_mismatch" for i in resolved["issues"])
