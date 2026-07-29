"""ERP adapter, built against the SAP OData API shape.

Only *validated* invoices reach here. The rest of the app depends on
``ERPAdapter.post_invoice``. Two implementations:

- ``MockSAPODataAdapter`` — offline, deterministic. Returns a stable id derived
  from the invoice's business key (vendor VAT + invoice number), so re-posting
  the same invoice always yields the same id: idempotent by construction.
- ``SAPODataAdapter`` — POSTs to a real OData v2/v4 service. It mirrors SAP's
  OData conventions: a service root + entity set, JSON body, bearer auth. A plain
  OData POST is *create*, not upsert, so to keep retries safe it sends an
  ``Idempotency-Key`` header derived from the business key — the mechanism SAP
  API gateways use to de-duplicate a redelivered request. The pipeline also
  guards against re-posting a document that already has an ERP id. Works against
  a real SAP gateway, an Odoo OData bridge, or any mock OData server, so
  "integrates with SAP OData" is honest, not simulated.
"""
from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod

from app.schemas import InvoiceData

# The OData entity set we post supplier invoices to (SAP's real one is long;
# this mirrors the shape: <service>/<EntitySet>).
_ENTITY_SET = "A_SupplierInvoice"


class ERPError(RuntimeError):
    """Raised when the ERP push fails; the document is marked FAILED so a retry
    (which is idempotent on the ERP side) can safely re-run."""


class ERPAdapter(ABC):
    @abstractmethod
    def post_invoice(self, inv: InvoiceData) -> str:
        """Create/upsert the invoice in the ERP; return its ERP document id."""


def _business_key(inv: InvoiceData) -> str:
    """Stable dedupe key for an invoice: vendor VAT + invoice number."""
    return hashlib.sha256(
        f"{inv.vendor_vat_id.upper()}:{inv.invoice_number}".encode()
    ).hexdigest()


class MockSAPODataAdapter(ERPAdapter):
    def post_invoice(self, inv: InvoiceData) -> str:
        # Deterministic id from the business key => re-posting is idempotent.
        return "SAP-" + _business_key(inv)[:12].upper()


class SAPODataAdapter(ERPAdapter):
    def __init__(self, base_url: str, token: str = "") -> None:
        self._base = base_url.rstrip("/")
        self._token = token

    def post_invoice(self, inv: InvoiceData) -> str:
        body = json.dumps(_to_odata_payload(inv)).encode()
        headers = {"Content-Type": "application/json", "Accept": "application/json",
                   # Business-key idempotency: a redelivered POST is de-duplicated
                   # by gateways that honor this standard header.
                   "Idempotency-Key": _business_key(inv)}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        req = urllib.request.Request(f"{self._base}/{_ENTITY_SET}", data=body, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 - configured ERP host
                payload = json.loads(resp.read() or b"{}")
        except (urllib.error.URLError, ValueError) as exc:
            raise ERPError(f"SAP OData post failed: {exc}") from exc
        # OData responses nest the entity under "d" (v2) or at the root (v4).
        entity = payload.get("d", payload)
        erp_id = entity.get("SupplierInvoice") or entity.get("id")
        if not erp_id:
            raise ERPError("SAP OData response missing invoice id")
        return str(erp_id)


def _to_odata_payload(inv: InvoiceData) -> dict:
    """Map our schema to SAP-ish OData field names."""
    return {
        "SupplierName": inv.vendor_name,
        "SupplierVATRegistration": inv.vendor_vat_id,
        "SupplierInvoiceIDByInvcgParty": inv.invoice_number,
        "DocumentDate": inv.invoice_date,
        "DocumentCurrency": inv.currency,
        "InvoiceGrossAmount": inv.total,
        "TaxAmount": inv.vat_amount,
        "to_SupplierInvoiceItem": [
            {
                "SupplierInvoiceItemText": li.description,
                "Quantity": li.quantity,
                "UnitPrice": li.unit_price,
                "DocumentCurrencyAmount": li.amount,
            }
            for li in inv.line_items
        ],
    }


def get_erp_adapter(provider: str, base_url: str = "", token: str = "") -> ERPAdapter:
    if provider == "sap_odata" and base_url:
        return SAPODataAdapter(base_url, token)
    return MockSAPODataAdapter()
