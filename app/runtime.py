"""Process-wide singletons: OCR, extractor, ERP adapter, LLM. All swappable via
env; defaults are offline-friendly (pdftext OCR, regex extractor, mock ERP)."""
from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.erp.adapter import ERPAdapter, get_erp_adapter
from app.extraction.extractor import Extractor, get_extractor
from app.llm.client import LLMClient
from app.ocr.ocr import OCRProvider, get_ocr_provider


@lru_cache
def get_llm_or_none() -> LLMClient | None:
    s = get_settings()
    has_key = (s.llm_provider == "anthropic" and s.anthropic_api_key) or (
        s.llm_provider == "openai" and s.openai_api_key
    )
    return LLMClient() if has_key else None


@lru_cache
def get_ocr() -> OCRProvider:
    return get_ocr_provider(get_settings().ocr_provider)


@lru_cache
def get_extractor_singleton() -> Extractor:
    # LLM extractor when a key is set, else the deterministic regex extractor.
    return get_extractor(get_llm_or_none())


@lru_cache
def get_erp() -> ERPAdapter:
    s = get_settings()
    return get_erp_adapter(s.erp_provider, s.erp_odata_base_url, s.erp_odata_token)
