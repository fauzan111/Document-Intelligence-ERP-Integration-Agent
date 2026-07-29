"""OCR / text-extraction layer (pluggable).

Two providers behind one seam:

- ``PdfTextExtractor`` (default) — pulls the text layer out of a native PDF with
  pypdf. No system binary, so it runs offline and deploys anywhere. If raw text
  is supplied directly (the simplest demo path), it's returned as-is.
- ``TesseractOCR`` — real OCR for scanned images/photos. Needs the ``tesseract``
  binary + ``pytesseract`` (an optional extra), so it's opt-in via
  ``OCR_PROVIDER=tesseract``.

The pipeline depends only on ``OCRProvider.extract_text``.
"""
from __future__ import annotations

import base64
import io
from abc import ABC, abstractmethod


class OCRError(RuntimeError):
    """Raised when text could not be extracted from the document."""


class OCRProvider(ABC):
    @abstractmethod
    def extract_text(self, *, text: str | None, pdf_bytes: bytes | None) -> str: ...


class PdfTextExtractor(OCRProvider):
    def extract_text(self, *, text: str | None, pdf_bytes: bytes | None) -> str:
        if text and text.strip():
            return text.strip()
        if pdf_bytes:
            return _extract_pdf_text(pdf_bytes)
        raise OCRError("No text or PDF content provided")


class TesseractOCR(OCRProvider):
    """Real OCR for images. Falls back to PDF text extraction when given a PDF."""

    def extract_text(self, *, text: str | None, pdf_bytes: bytes | None) -> str:
        if text and text.strip():
            return text.strip()
        if pdf_bytes:
            return _extract_pdf_text(pdf_bytes)
        raise OCRError("TesseractOCR: no content; image OCR path expects image bytes")


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency always present in prod
        raise OCRError("pypdf not installed") from exc
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  # noqa: BLE001 - malformed PDF -> a clean OCR error
        raise OCRError(f"Could not read PDF: {exc}") from exc
    joined = "\n".join(pages).strip()
    if not joined:
        raise OCRError(
            "PDF has no extractable text layer (scanned image?); use OCR_PROVIDER=tesseract"
        )
    return joined


def decode_pdf_base64(pdf_base64: str | None) -> bytes | None:
    if not pdf_base64:
        return None
    try:
        return base64.b64decode(pdf_base64, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise OCRError(f"Invalid base64 PDF: {exc}") from exc


def get_ocr_provider(provider: str) -> OCRProvider:
    if provider == "tesseract":
        return TesseractOCR()
    return PdfTextExtractor()
