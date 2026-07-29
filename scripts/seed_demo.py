"""Seed the document agent with a mix of invoices so you can see valid ->
ERP push and invalid -> exception queue in one run.

    python scripts/seed_demo.py --base-url http://localhost:8000
"""
from __future__ import annotations

import argparse
import json
import urllib.request
import uuid

# Inlined so the script is self-contained (can target a remote URL with no
# access to the app package). Mirrors app/sample_invoices.py.
SAMPLES = {
    "valid": (
        "Vendor: Rossi Manifattura SRL\nVAT: IT07643520567\n"
        "Invoice: INV-2026-000123\nDate: 2026-03-14\nCurrency: EUR\n"
        "- Steel brackets | qty 100 | unit 4.50 | amount 450.00\n"
        "- Assembly labor | qty 10 | unit 35.00 | amount 350.00\n"
        "Subtotal: 800.00\nVAT amount: 176.00\nTotal: 976.00\n"
    ),
    "bad_totals": (
        "Vendor: Bianchi Forniture SPA\nVAT: IT00743110157\n"
        "Invoice: INV-2026-000200\nDate: 2026-03-20\nCurrency: EUR\n"
        "- Packaging film | qty 50 | unit 2.00 | amount 100.00\n"
        "Subtotal: 100.00\nVAT amount: 22.00\nTotal: 150.00\n"
    ),
    "bad_vat": (
        "Vendor: Verdi Componenti SRL\nVAT: IT12345678901\n"
        "Invoice: INV-2026-000300\nDate: 2026-03-22\nCurrency: EUR\n"
        "- Sensor modules | qty 20 | unit 15.00 | amount 300.00\n"
        "Subtotal: 300.00\nVAT amount: 66.00\nTotal: 366.00\n"
    ),
}


def _post(base_url: str, path: str, payload: dict, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(base_url + path, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - local demo target
        return json.loads(resp.read())


def _get(base_url: str, path: str, token: str) -> dict:
    req = urllib.request.Request(base_url + path, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - local demo target
        return json.loads(resp.read())


def main(base_url: str) -> None:
    tenant = _post(base_url, "/tenants/signup", {"name": f"Demo Mfg {uuid.uuid4().hex[:6]}"})
    token = tenant["access_token"]
    print(f"tenant: {tenant['tenant_id']}\ntoken:  {token}\n")

    for name, text in SAMPLES.items():
        out = _post(base_url, "/documents", {"filename": f"{name}.txt", "text": text}, token=token)
        codes = ", ".join(i["code"] for i in out["issues"]) or "-"
        print(f"{name:11} -> {out['status']:14} erp={out['erp_record_id'] or '-'}  issues={codes}")

    queue = _get(base_url, "/exceptions", token)
    print(f"\nexception queue: {len(queue)} document(s) awaiting a human")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    main(parser.parse_args().base_url)
