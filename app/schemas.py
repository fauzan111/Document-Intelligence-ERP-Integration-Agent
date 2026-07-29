"""Pydantic schemas — the structured contract the LLM extracts into and the
deterministic validator checks. This IS the "clean, ERP-shaped record"."""
from __future__ import annotations

from pydantic import BaseModel, Field


class LineItem(BaseModel):
    description: str = ""
    quantity: float = 0.0
    unit_price: float = 0.0
    amount: float = 0.0  # expected == quantity * unit_price (validator checks this)


class InvoiceData(BaseModel):
    """Structured invoice. All numeric fields default to 0 so a partial LLM
    extraction still yields a well-typed object the validator can inspect."""

    vendor_name: str = ""
    vendor_vat_id: str = ""
    invoice_number: str = ""
    invoice_date: str = ""  # ISO-ish string; format-checked by the validator
    currency: str = "EUR"
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: float = 0.0
    vat_amount: float = 0.0
    total: float = 0.0


class ValidationIssue(BaseModel):
    field: str
    code: str        # machine-readable, e.g. "vat_checksum", "totals_mismatch"
    message: str


class DocumentUploadIn(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    # One of the following supplies the document content:
    #  - text: raw invoice text (or already-OCR'd text) — simplest demo path
    #  - pdf_base64: a base64 PDF; the OCR layer extracts its text
    text: str | None = None
    pdf_base64: str | None = None


class DocumentOut(BaseModel):
    id: str
    filename: str
    status: str                    # DocumentStatus value
    extracted: InvoiceData | None
    issues: list[ValidationIssue]
    erp_record_id: str | None
    extracted_by: str | None       # "llm" | "code"
