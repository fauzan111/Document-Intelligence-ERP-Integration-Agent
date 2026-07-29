"""The deterministic validation layer — the architectural centerpiece.

'LLMs extract, code validates.' These tests pin the code half: same input,
same verdict, no model involved. Includes the real Italian Partita IVA checksum.
"""
from __future__ import annotations

import pytest

from app.schemas import InvoiceData, LineItem
from app.validation.validator import (
    _italian_vat_checksum_ok,
    is_valid,
    validate_invoice,
)


def _good_invoice() -> InvoiceData:
    return InvoiceData(
        vendor_name="Rossi Manifattura SRL", vendor_vat_id="IT07643520567",
        invoice_number="INV-1", invoice_date="2026-03-14", currency="EUR",
        line_items=[
            LineItem(description="A", quantity=100, unit_price=4.5, amount=450.0),
            LineItem(description="B", quantity=10, unit_price=35.0, amount=350.0),
        ],
        subtotal=800.0, vat_amount=176.0, total=976.0,
    )


def test_clean_invoice_passes():
    assert is_valid(_good_invoice())
    assert validate_invoice(_good_invoice()) == []


@pytest.mark.parametrize("vat,ok", [
    ("07643520567", True),    # real valid Partita IVA
    ("00743110157", True),    # real valid Partita IVA
    ("12345678901", False),   # checksum fails
    ("07643520560", False),   # last digit wrong
])
def test_italian_vat_checksum(vat, ok):
    assert _italian_vat_checksum_ok(vat) is ok


def test_bad_vat_checksum_flagged():
    inv = _good_invoice()
    inv.vendor_vat_id = "IT12345678901"
    codes = {i.code for i in validate_invoice(inv)}
    assert "vat_checksum" in codes


def test_totals_mismatch_flagged():
    inv = _good_invoice()
    inv.total = 999.0  # subtotal+vat = 976 != 999
    codes = {i.code for i in validate_invoice(inv)}
    assert "totals_mismatch" in codes


def test_line_item_math_flagged():
    inv = _good_invoice()
    inv.line_items[0].amount = 999.0  # 100*4.5 = 450 != 999
    codes = {i.code for i in validate_invoice(inv)}
    assert "line_math" in codes


def test_subtotal_mismatch_flagged():
    inv = _good_invoice()
    inv.subtotal = 700.0  # line items sum to 800
    inv.total = 876.0     # keep subtotal+vat==total so only subtotal trips
    codes = {i.code for i in validate_invoice(inv)}
    assert "subtotal_mismatch" in codes


def test_missing_required_fields_flagged():
    inv = InvoiceData(total=10.0)  # almost everything missing
    codes = {i.code for i in validate_invoice(inv)}
    assert "required" in codes


def test_rounding_within_tolerance_passes():
    inv = _good_invoice()
    inv.total = 976.01  # within default 0.02 tolerance
    assert is_valid(inv)


def test_dashless_date_rejected():
    # date.fromisoformat accepts "20260314" on 3.11+; the validator must not.
    inv = _good_invoice()
    inv.invoice_date = "20260314"
    codes = {i.code for i in validate_invoice(inv)}
    assert "date_format" in codes


def test_non_positive_total_flagged():
    inv = _good_invoice()
    inv.line_items = []
    inv.subtotal = 0.0
    inv.vat_amount = 0.0
    inv.total = 0.0
    codes = {i.code for i in validate_invoice(inv)}
    assert "non_positive" in codes
