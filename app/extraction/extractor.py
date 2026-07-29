"""Structured extraction: turn OCR'd invoice text into a typed ``InvoiceData``.

Two extractors behind one seam:

- ``LLMExtractor`` — asks the LLM to return strict JSON matching the schema, then
  parses it into ``InvoiceData``. Robust to messy layouts.
- ``RegexExtractor`` (offline fallback) — a deterministic parser for the demo
  invoice format, so the whole pipeline runs with no API key.

Extraction is intentionally the *only* place the LLM touches the numbers. It
proposes values; the deterministic validator (next stage) is what decides
whether they are trustworthy — "LLMs extract, code validates".
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod

from app.llm.client import LLMClient
from app.schemas import InvoiceData, LineItem

_SYSTEM = (
    "You extract invoice fields into JSON. Return ONLY a JSON object with keys: "
    "vendor_name, vendor_vat_id, invoice_number, invoice_date (YYYY-MM-DD), currency, "
    "line_items (array of {description, quantity, unit_price, amount}), subtotal, "
    "vat_amount, total. Use numbers for numeric fields. Do not invent values not "
    "present in the text; leave unknown strings empty and unknown numbers 0."
)


class Extractor(ABC):
    name: str

    @abstractmethod
    def extract(self, text: str) -> InvoiceData: ...


class LLMExtractor(Extractor):
    name = "llm"

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def extract(self, text: str) -> InvoiceData:
        resp = self._llm.complete(system=_SYSTEM, prompt=text, max_tokens=1200)
        payload = _first_json_object(resp.text)
        if payload is None:
            return InvoiceData()
        return _coerce_invoice(payload)


class RegexExtractor(Extractor):
    """Deterministic parser for the demo invoice text format. Not a general OCR
    parser — it exists so the pipeline is fully runnable offline."""

    name = "code"

    def extract(self, text: str) -> InvoiceData:
        inv = InvoiceData()
        inv.vendor_name = _field(text, r"(?:vendor|supplier|from)\s*[:\-]\s*(.+)")
        vat_pattern = r"(?:vat id|partita iva|p\.?\s*iva|vat)\s*[:\-]\s*([A-Za-z0-9 ]+)"
        inv.vendor_vat_id = _field(text, vat_pattern).replace(" ", "").upper()
        num_pattern = r"(?:invoice no\.?|invoice|number)\s*[:\-]\s*([A-Za-z0-9\-/]+)"
        inv.invoice_number = _field(text, num_pattern)
        inv.invoice_date = _field(text, r"(?:date)\s*[:\-]\s*([0-9]{4}-[0-9]{2}-[0-9]{2})")
        cur = _field(text, r"(?:currency)\s*[:\-]\s*([A-Za-z]{3})")
        inv.currency = cur.upper() or "EUR"

        for m in re.finditer(
            r"(?im)^\s*-\s*(.+?)\s*\|\s*qty\s*([0-9.]+)\s*\|\s*unit\s*([0-9.]+)\s*\|\s*amount\s*([0-9.]+)\s*$",
            text,
        ):
            inv.line_items.append(LineItem(
                description=m.group(1).strip(), quantity=_num(m.group(2)),
                unit_price=_num(m.group(3)), amount=_num(m.group(4)),
            ))

        inv.subtotal = _num(_field(text, r"(?:subtotal)\s*[:\-]\s*([0-9.]+)"))
        inv.vat_amount = _num(_field(text, r"(?:vat amount|tax)\s*[:\-]\s*([0-9.]+)"))
        # \btotal\b so "Subtotal:" (no word boundary before "total") isn't matched.
        inv.total = _num(_field(text, r"\btotal\b\s*[:\-]\s*([0-9.]+)"))
        return inv


# --- helpers ---------------------------------------------------------------- #

def _field(text: str, pattern: str) -> str:
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _num(s: str) -> float:
    # Strip thousands separators so "1,234.00" parses correctly.
    try:
        return float(str(s).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def _first_json_object(text: str) -> dict | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _coerce_invoice(payload: dict) -> InvoiceData:
    items = [
        LineItem(
            description=str(li.get("description", "")),
            quantity=_num(str(li.get("quantity", 0))),
            unit_price=_num(str(li.get("unit_price", 0))),
            amount=_num(str(li.get("amount", 0))),
        )
        for li in payload.get("line_items", []) or []
        if isinstance(li, dict)
    ]
    return InvoiceData(
        vendor_name=str(payload.get("vendor_name", "")),
        vendor_vat_id=str(payload.get("vendor_vat_id", "")).replace(" ", "").upper(),
        invoice_number=str(payload.get("invoice_number", "")),
        invoice_date=str(payload.get("invoice_date", "")),
        currency=str(payload.get("currency", "EUR")) or "EUR",
        line_items=items,
        subtotal=_num(str(payload.get("subtotal", 0))),
        vat_amount=_num(str(payload.get("vat_amount", 0))),
        total=_num(str(payload.get("total", 0))),
    )


def get_extractor(llm: LLMClient | None) -> Extractor:
    return LLMExtractor(llm) if llm is not None else RegexExtractor()
