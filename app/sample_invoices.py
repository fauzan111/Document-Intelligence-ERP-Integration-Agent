"""Sample invoice texts for demos and tests. Kept in the app package so the
seed script, the frontend defaults, and the tests all share one source of truth.

The format matches the RegexExtractor's grammar so the whole pipeline runs
offline. VAT ids below carry valid Italian Partita IVA checksums.
"""
from __future__ import annotations

# A clean, fully-reconciling invoice -> passes validation -> pushed to ERP.
VALID_INVOICE = """\
Vendor: Rossi Manifattura SRL
VAT: IT07643520567
Invoice: INV-2026-000123
Date: 2026-03-14
Currency: EUR
- Steel brackets | qty 100 | unit 4.50 | amount 450.00
- Assembly labor | qty 10 | unit 35.00 | amount 350.00
Subtotal: 800.00
VAT amount: 176.00
Total: 976.00
"""

# Totals do not reconcile (subtotal+vat != total) -> exception queue.
BAD_TOTALS_INVOICE = """\
Vendor: Bianchi Forniture SPA
VAT: IT00743110157
Invoice: INV-2026-000200
Date: 2026-03-20
Currency: EUR
- Packaging film | qty 50 | unit 2.00 | amount 100.00
Subtotal: 100.00
VAT amount: 22.00
Total: 150.00
"""

# Invalid Italian VAT checksum -> exception queue.
BAD_VAT_INVOICE = """\
Vendor: Verdi Componenti SRL
VAT: IT12345678901
Invoice: INV-2026-000300
Date: 2026-03-22
Currency: EUR
- Sensor modules | qty 20 | unit 15.00 | amount 300.00
Subtotal: 300.00
VAT amount: 66.00
Total: 366.00
"""

SAMPLES = {
    "valid": VALID_INVOICE,
    "bad_totals": BAD_TOTALS_INVOICE,
    "bad_vat": BAD_VAT_INVOICE,
}
