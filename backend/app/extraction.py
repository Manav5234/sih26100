"""Document intelligence: text layer first, OCR fallback, LLM field extraction.

Pipeline: PDF -> per-page text (pdfplumber/PyMuPDF text layer, else OCR)
-> LLM strict-JSON read -> evidence objects
{field_name, value, confidence, page, extraction_method}.

The LLM reads values; it never invents them. Anything not fully legible
comes back null, which is what surfaces as `unreadable` downstream.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field as dc_field

import httpx
import numpy as np
import pymupdf
from PIL import Image

from app import llm
from app.ocr import ocr_image

logger = logging.getLogger(__name__)

# Extraction schemas per doc_type. Phase 3: identity docs. Phase 6.7:
# financial / OEM / local-content evidence — same pipeline, null over guessing.
DOC_SCHEMAS: dict[str, list[str]] = {
    "PAN": ["pan", "name"],
    "GST": ["gstin", "legal_name", "status"],
    "UDYAM": ["udyam_number", "enterprise_name", "category"],
    "FINANCIAL": ["turnover_cr", "financial_year", "entity_name"],
    "OEM_AUTHORIZATION": ["oem_name", "authorization_statement", "entity_name"],
    "LOCAL_CONTENT": ["local_content_pct", "entity_name"],
}

# Identifier that must be readable for the document to count as usable.
# Doc types without an entry (financial/OEM/local content) are free-form:
# no key identifier, so no format check — values are evidence, not IDs.
KEY_FIELD: dict[str, str] = {"PAN": "pan", "GST": "gstin", "UDYAM": "udyam_number"}

# Legal formats for the key identifiers. A truncated / redacted / garbled ID
# (e.g. OCR read only the visible prefix) must come back null — never stored
# as evidence as if it were complete. Trust-boundary check, not a guess:
# validated against the documented format, never repaired.
KEY_FORMATS: dict[str, str] = {
    "PAN": r"^[A-Z]{5}[0-9]{4}[A-Z]$",
    "GST": r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$",
    # 7 trailing digits is the published Udyam format; some registry prints
    # show 8 — accept both rather than reject a legible, valid ID.
    "UDYAM": r"^UDYAM-[A-Z]{2}-[0-9]{2}-[0-9]{7,8}$",
}

MIN_TEXT_LAYER_CHARS = 20   # fewer extractable characters than this = image-only page
OCR_DPI = 200
DEFAULT_CONF_TEXT = 0.7
DEFAULT_CONF_OCR = 0.5
TEXT_EXCERPT_CHARS = 1000


@dataclass
class PageText:
    page: int
    text: str
    method: str                  # 'text_layer' | 'ocr'
    ocr_confidence: float | None = None


@dataclass
class FieldEvidence:
    field_name: str
    value: str | None
    confidence: float
    page: int | None
    extraction_method: str | None


@dataclass
class ExtractionResult:
    method: str | None           # document-level: 'ocr' if any page needed OCR
    raw_text_excerpt: str | None
    fields: list[FieldEvidence] = dc_field(default_factory=list)


def read_pages(path: str) -> list[PageText]:
    """Per-page text. Image-only pages go through OCR instead of the text layer."""
    pages: list[PageText] = []
    doc = pymupdf.open(path)
    try:
        for index, page in enumerate(doc, start=1):
            text = (page.get_text("text") or "").strip()
            if len(text) >= MIN_TEXT_LAYER_CHARS:
                pages.append(PageText(page=index, text=text, method="text_layer"))
                continue
            image = _page_to_rgb(page)
            ocr_text, ocr_conf, engine = ocr_image(image)
            logger.info(
                "ocr_fallback page=%s engine=%s mean_confidence=%.2f chars=%s",
                index, engine, ocr_conf, len(ocr_text),
            )
            pages.append(PageText(page=index, text=ocr_text.strip(), method="ocr",
                                  ocr_confidence=ocr_conf))
    finally:
        doc.close()
    return pages


def extract_document(path: str, doc_type: str) -> ExtractionResult:
    """Read every page, run the LLM per page, merge into evidence objects."""
    if doc_type not in DOC_SCHEMAS:
        raise ValueError(f"unsupported doc_type: {doc_type}")
    keys = DOC_SCHEMAS[doc_type]

    pages = read_pages(path)
    method = (
        "ocr" if any(p.method == "ocr" for p in pages)
        else "text_layer" if pages
        else None
    )
    excerpt = "\n\n".join(p.text for p in pages if p.text)[:TEXT_EXCERPT_CHARS] or None

    values: dict[str, str | None] = {k: None for k in keys}
    confidences: dict[str, float] = {}
    found_on: dict[str, int | None] = {k: None for k in keys}

    for page in pages:
        if not page.text.strip():
            continue
        data = _llm_read(page.text, doc_type, keys)
        base = DEFAULT_CONF_OCR if page.method == "ocr" else DEFAULT_CONF_TEXT
        model_conf = _confidence_map(data.get("confidence"), keys)
        for key in keys:
            if values[key] is not None:
                continue
            value = _clean(data.get(key))
            if value is None:
                continue
            values[key] = value
            confidences[key] = model_conf.get(key, base)
            found_on[key] = page.page

    key = KEY_FIELD.get(doc_type)
    if key and values[key] is not None:
        candidate = _id_candidate(doc_type, values[key])
        if not re.match(KEY_FORMATS[doc_type], candidate):
            logger.info("key_identifier_rejected doc_type=%s value=%r (not a complete %s id)",
                        doc_type, values[key], doc_type)
            values[key] = None
            confidences.pop(key, None)
            found_on[key] = None

    fields = [
        FieldEvidence(
            field_name=key,
            value=values[key],
            confidence=round(confidences.get(key, 0.0), 3),
            page=found_on[key],
            extraction_method=method,
        )
        for key in keys
    ]
    return ExtractionResult(method=method, raw_text_excerpt=excerpt, fields=fields)


def _id_candidate(doc_type: str, value: str) -> str:
    """OCR gaps and stray punctuation normalized before the format check."""
    if doc_type == "UDYAM":                     # format has '-' separators
        return re.sub(r"[^A-Z0-9]+", "-", value.upper()).strip("-")
    return re.sub(r"[^A-Z0-9]", "", value.upper())   # PAN / GSTIN: no separators


def _page_to_rgb(page: pymupdf.Page) -> np.ndarray:
    pix = page.get_pixmap(dpi=OCR_DPI)
    mode = "RGBA" if pix.alpha else ("RGB" if pix.n >= 3 else "L")
    image = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
    return np.array(image.convert("RGB"))


def _llm_read(text: str, doc_type: str, keys: list[str]) -> dict:
    prompt = f"Document type: {doc_type}\n\nDocument text:\n{text}"
    try:
        return llm.extract_json(prompt, keys=keys)
    except llm.LLMError as exc:
        logger.warning("llm_parse_failed doc_type=%s: %s", doc_type, exc)
        return {}
    except httpx.HTTPError as exc:
        logger.warning("llm_unreachable doc_type=%s: %s", doc_type, exc)
        return {}


def _clean(value) -> str | None:
    """Accept only real scalars — dicts/lists/bools are not identifiers."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _confidence_map(raw, keys: list[str]) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float] = {}
    for key in keys:
        value = raw.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1:
            out[key] = float(value)
    return out
