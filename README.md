# Document Intelligence & ERP Integration Agent

An agent that ingests invoices, extracts structured data (OCR + LLM), **validates
it against deterministic business rules**, and pushes clean records into a
SAP-shaped ERP — routing anything that fails validation to a human exception
queue instead of silently guessing. This targets Italy's stated enterprise
preference: **ERP-integration depth over novel features.**

Built on [`agent-platform-foundation`](../agent-platform-foundation) — same
multi-tenancy, audit-log, provider-agnostic-LLM, and observability spine.

## LLMs extract, code validates

> This is the architectural detail production teams look for, so it's the loud
> part of this project. The LLM's only job is to **propose** structured fields
> from messy document text. Whether those fields are **trustworthy** is decided
> by a purely deterministic validation layer (`app/validation/validator.py`) —
> regex and arithmetic, no model. A record reaches the ERP only if it passes
> *every* rule; otherwise it goes to a human with the exact field that failed.

Deterministic rules enforced:
- **Required fields** present (vendor, VAT id, invoice number, date, total).
- **Italian Partita IVA checksum** — the real Luhn-style check digit, not just a
  format regex. (Plus a general EU VAT format gate.)
- **Line-item math** — `quantity × unit_price == amount` per line.
- **Subtotal reconciliation** — line items sum to the subtotal.
- **Totals reconciliation** — `subtotal + VAT == total`.
- **Positive total**, valid ISO date.

Each of these is pinned by a test in `tests/unit/test_validation.py`.

## Architecture

```
Document (PDF / scan / text)
   → OCR / text extraction        [pluggable: pypdf offline · Tesseract for scans]
   → LLM structured extraction    [Pydantic InvoiceData; regex extractor offline]
   → deterministic validation     [regex + arithmetic — NOT LLM-judged]
   → valid?  → push to ERP        [SAP OData-shaped adapter; mock offline]
     invalid → human exception queue with the specific failing field(s)
   → every extract / validate / push → AuditLog (tenant_id, decided_by)
```

The routing decision (ERP vs exception) is made by the deterministic validator,
not the LLM — see the LangGraph flow in `app/agents/extraction_graph.py`.

## Real ERP integration shape

The ERP adapter (`app/erp/adapter.py`) is built against **SAP's OData** contract:
a service root + entity set (`A_SupplierInvoice`), JSON body with SAP-style field
names, bearer auth, and OData v2/v4 response parsing. `ERP_PROVIDER=mock` runs
offline (a stable id from the vendor VAT + invoice number, i.e. idempotent
upsert semantics); `ERP_PROVIDER=sap_odata` + a base URL posts to a real OData
service (SAP gateway, an Odoo OData bridge, or a mock OData server).

## Runs fully offline (no API key)

`pdftext` OCR extracts native-PDF text (or takes raw text directly) with no
system binary. No LLM key → the deterministic **regex extractor** parses the demo
invoice format. `ERP_PROVIDER=mock` → deterministic SAP-shaped ids. So the whole
pipeline runs from one container with zero secrets.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest tests/unit -q            # 20 tests, no external services

make run                        # http://localhost:8000  (offline)
make demo                       # valid invoice → ERP; bad totals / bad VAT → exception queue

docker compose up --build       # full stack with Postgres + Redis
```

Open **http://localhost:8000/** for the console: load a sample invoice, watch it
either post to the ERP or land in the exception queue with the exact failing
field, then fix a value and re-file (re-validated by the same rules).

### API

| Method | Path | Purpose |
|---|---|---|
| POST | `/tenants/signup` | Create a tenant; returns a token |
| POST | `/documents` | Submit an invoice (text or base64 PDF); idempotent on content |
| GET  | `/documents` | List this tenant's documents |
| GET  | `/exceptions` | The human exception queue (failed validation) |
| POST | `/exceptions/{id}/resolve` | Submit corrected fields; re-validated, then pushed if valid |
| GET  | `/health` | Liveness |

## Deploy live (Render, one blueprint)

The repo ships a [`render.yaml`](./render.yaml): **New → Blueprint → connect this
repo → Apply**. Render provisions the web service + Postgres and auto-deploys on
push. Add `ANTHROPIC_API_KEY` for LLM extraction, or `ERP_PROVIDER=sap_odata` +
`ERP_ODATA_BASE_URL`/`ERP_ODATA_TOKEN` for a real ERP push, in the Environment tab.

> Free-tier notes: the web service sleeps after ~15 min idle (~30s cold start);
> free Postgres expires after 90 days.

## Tech stack

Python 3.12 · FastAPI · LangGraph · SQLAlchemy · pypdf · Celery/Redis · structlog
· Docker Compose · GitHub Actions · pytest. ERP adapter targets SAP OData;
optional Tesseract OCR for scanned images.
