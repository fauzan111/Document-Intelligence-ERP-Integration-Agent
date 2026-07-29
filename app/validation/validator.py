"""Deterministic validation layer — the architectural centerpiece.

**LLMs extract, code validates.** Nothing here calls an LLM. Every check is
regex or arithmetic, so the same input always yields the same verdict — exactly
what a production/finance team requires before a record touches a system of
record. A document only advances to the ERP if it passes *every* rule; any
failure produces a precise ``ValidationIssue`` (which field, why) and routes the
document to the human exception queue.

Rules:
1. Required fields present (vendor, VAT id, invoice number, date, total).
2. Invoice date is a real ISO ``YYYY-MM-DD`` date.
3. VAT id has a valid format; Italian ``IT``+11-digit ids also pass the official
   Partita IVA checksum (a Luhn-style check digit).
4. Each line item: ``quantity * unit_price == amount`` (within tolerance).
5. Line items sum to ``subtotal`` (within tolerance).
6. ``subtotal + vat_amount == total`` (within tolerance).
7. ``total > 0``.
"""
from __future__ import annotations

import re
from datetime import date

from app.schemas import InvoiceData, ValidationIssue

# EU VAT: 2-letter country code + up to 12 alphanumerics (loose format gate).
_EU_VAT_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{2,12}$")


def validate_invoice(inv: InvoiceData, *, tolerance: float = 0.02) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    # 1. Required fields.
    for field, value in (
        ("vendor_name", inv.vendor_name),
        ("vendor_vat_id", inv.vendor_vat_id),
        ("invoice_number", inv.invoice_number),
        ("invoice_date", inv.invoice_date),
    ):
        if not str(value).strip():
            issues.append(ValidationIssue(field=field, code="required",
                                          message=f"{field} is missing"))

    # 2. Date format.
    if inv.invoice_date and not _is_iso_date(inv.invoice_date):
        issues.append(ValidationIssue(field="invoice_date", code="date_format",
                                      message="invoice_date must be YYYY-MM-DD"))

    # 3. VAT id format + Italian checksum.
    issues.extend(_validate_vat(inv.vendor_vat_id))

    # 4. Per-line arithmetic.
    line_sum = 0.0
    for i, li in enumerate(inv.line_items):
        expected = round(li.quantity * li.unit_price, 2)
        if abs(expected - li.amount) > tolerance:
            issues.append(ValidationIssue(
                field=f"line_items[{i}].amount", code="line_math",
                message=f"quantity*unit_price={expected} != amount={li.amount}",
            ))
        line_sum += li.amount

    # 5. Line items reconcile to subtotal (only if we have line items).
    if inv.line_items and abs(round(line_sum, 2) - inv.subtotal) > tolerance:
        issues.append(ValidationIssue(
            field="subtotal", code="subtotal_mismatch",
            message=f"sum(line_items)={round(line_sum, 2)} != subtotal={inv.subtotal}",
        ))

    # 6. subtotal + vat == total.
    if abs(round(inv.subtotal + inv.vat_amount, 2) - inv.total) > tolerance:
        issues.append(ValidationIssue(
            field="total", code="totals_mismatch",
            message=f"subtotal+vat={round(inv.subtotal + inv.vat_amount, 2)} != total={inv.total}",
        ))

    # 7. Positive total.
    if inv.total <= 0:
        issues.append(ValidationIssue(field="total", code="non_positive",
                                      message="total must be greater than 0"))

    return issues


def is_valid(inv: InvoiceData, *, tolerance: float = 0.02) -> bool:
    return not validate_invoice(inv, tolerance=tolerance)


# --- VAT ------------------------------------------------------------------- #

def _validate_vat(vat: str) -> list[ValidationIssue]:
    vat = (vat or "").replace(" ", "").upper()
    if not vat:
        return []  # missing handled by the required-fields rule
    if not _EU_VAT_RE.match(vat):
        return [ValidationIssue(field="vendor_vat_id", code="vat_format",
                                message="VAT id is not a valid EU format")]
    if vat.startswith("IT"):
        digits = vat[2:]
        if not (len(digits) == 11 and digits.isdigit()):
            return [ValidationIssue(field="vendor_vat_id", code="vat_it_length",
                                    message="Italian VAT must be IT + 11 digits")]
        if not _italian_vat_checksum_ok(digits):
            return [ValidationIssue(field="vendor_vat_id", code="vat_checksum",
                                    message="Italian Partita IVA checksum failed")]
    return []


def _italian_vat_checksum_ok(digits: str) -> bool:
    """Official Partita IVA check: Luhn-style over the first 10 digits, the 11th
    is the check digit."""
    total = 0
    for i, ch in enumerate(digits[:10]):
        n = int(ch)
        if i % 2 == 1:  # even position (1-based): double
            n *= 2
            if n > 9:
                n -= 9
        total += n
    check = (10 - (total % 10)) % 10
    return check == int(digits[10])


_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _is_iso_date(value: str) -> bool:
    # Require the exact YYYY-MM-DD shape: date.fromisoformat alone accepts
    # dashless forms like "20260314" on Python 3.11+, which we must reject.
    if not _ISO_DATE_RE.match(value):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False
