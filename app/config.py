"""Application settings, loaded from environment. Single source of truth."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    app_name: str = "docintel-erp-agent"
    environment: Literal["dev", "staging", "prod"] = "dev"
    log_level: str = "INFO"

    # --- Database (multi-tenant; every row is tenant-scoped) ---
    database_url: str = "postgresql+psycopg2://agent:agent@localhost:5432/agentdb"

    # --- Async workers ---
    redis_url: str = "redis://localhost:6379/0"

    # --- LLM (provider-agnostic client) ---
    llm_provider: Literal["anthropic", "openai"] = "anthropic"
    llm_model: str = "claude-opus-4-8"
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # --- OCR (pluggable). "pdftext" extracts native-PDF text with no system
    #     binary (offline-friendly). "tesseract" does real image OCR but needs
    #     the tesseract binary installed. ---
    ocr_provider: Literal["pdftext", "tesseract"] = "pdftext"

    # --- ERP adapter (built against SAP OData shape). "mock" works offline;
    #     "sap_odata" posts to a real OData service when a base URL is set. ---
    erp_provider: Literal["mock", "sap_odata"] = "mock"
    erp_odata_base_url: str = ""
    erp_odata_token: str = ""

    # --- Validation ---
    # Absolute tolerance (in currency units) for arithmetic reconciliation, so
    # rounding on line items doesn't trip a false exception.
    amount_tolerance: float = 0.02

    # --- Auth ---
    jwt_secret: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"


@lru_cache
def get_settings() -> Settings:
    return Settings()
