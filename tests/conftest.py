"""Test configuration. Point the app at a SQLite DB and dummy secret *before*
any app module (and its cached settings) is imported, so tests run with no
external Postgres/Redis/LLM/ERP dependencies.

No provider keys: extraction uses the deterministic regex extractor, OCR uses
the pdftext/direct-text path, and the ERP push uses the mock SAP adapter. Zero
network calls.
"""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///./test_docintel.sqlite")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ENVIRONMENT", "dev")
os.environ.setdefault("OCR_PROVIDER", "pdftext")
os.environ.setdefault("ERP_PROVIDER", "mock")
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""
