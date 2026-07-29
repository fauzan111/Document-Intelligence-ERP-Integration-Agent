"""Regex extractor + ERP adapter idempotency."""
from __future__ import annotations

from app.erp.adapter import MockSAPODataAdapter
from app.extraction.extractor import RegexExtractor
from app.sample_invoices import VALID_INVOICE


def test_regex_extractor_parses_demo_invoice():
    inv = RegexExtractor().extract(VALID_INVOICE)
    assert inv.vendor_name == "Rossi Manifattura SRL"
    assert inv.vendor_vat_id == "IT07643520567"
    assert inv.invoice_number == "INV-2026-000123"
    assert inv.invoice_date == "2026-03-14"
    assert len(inv.line_items) == 2
    assert inv.line_items[0].amount == 450.0
    assert inv.subtotal == 800.0
    assert inv.vat_amount == 176.0
    assert inv.total == 976.0


def test_mock_erp_push_is_idempotent_by_business_key():
    erp = MockSAPODataAdapter()
    inv = RegexExtractor().extract(VALID_INVOICE)
    # Same vendor VAT + invoice number => same ERP id (upsert semantics).
    assert erp.post_invoice(inv) == erp.post_invoice(inv)
    assert erp.post_invoice(inv).startswith("SAP-")


def test_vat_id_normalized_uppercase():
    inv = RegexExtractor().extract("VAT: it07643520567\nTotal: 1.00")
    assert inv.vendor_vat_id == "IT07643520567"


def test_thousands_separator_parsed():
    from app.extraction.extractor import _num
    assert _num("1,234.00") == 1234.0
    assert _num("976.00") == 976.0
