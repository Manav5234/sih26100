"""LLM client for schema-strict JSON field extraction.

Talks to a local Ollama server (no external API). JSON mode only, temperature 0.
The model is never allowed to decide compliance — it only reads fields off text.
"""
from __future__ import annotations

import json
import re

import httpx

from app.config import settings

# ponytail: 120s covers first-call model load (~10-30s for a 9B model on CPU).
DEFAULT_TIMEOUT = 120.0


class LLMError(Exception):
    """Raised when the model output cannot be parsed as JSON."""


_SYSTEM_PROMPT = """You extract fields from Indian procurement documents.
Return ONLY valid JSON with exactly these keys: {keys}.
Rules:
- Use null for any value that is not fully and confidently present in the text.
- Never infer, complete or guess a partially visible identifier (PAN, GSTIN,
  Udyam registration number). It is either fully legible in the text or null.
- OCR often merges words with no space ("ABCTECHNOLOGIESPVTLTD"). Restore
  spaces at word boundaries in entity/person names — e.g. write
  "ABC TECHNOLOGIES PVT LTD" — but never invent words that are not in the text.
- Optionally add a "confidence" object mapping each key to a number between 0
  and 1 reflecting how certain you are of that value. Omit it if unsure.
- Numeric values (amounts, percentages) as plain numbers without symbols or
  units, e.g. 12.40 or 45 — never "Rs. 12.40" or "45%"."""


def extract_json(user_prompt: str, *, keys: list[str], timeout: float = DEFAULT_TIMEOUT) -> dict:
    """Call the local model and return its parsed JSON object."""
    body = {
        "model": settings.llm_model,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT.format(keys=", ".join(keys))},
            {"role": "user", "content": user_prompt},
        ],
    }
    resp = httpx.post(
        f"{settings.llm_base_url}/api/chat",
        json=body,
        timeout=timeout,
    )
    resp.raise_for_status()
    content = resp.json()["message"]["content"]
    return _parse_json(content)


def _parse_json(content: str) -> dict:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        # ponytail: tolerate preamble around the object rather than failing the upload.
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            raise LLMError(f"model returned no JSON object: {content[:200]}") from None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise LLMError(f"model returned unparseable JSON: {content[:200]}") from exc
    if not isinstance(data, dict):
        raise LLMError(f"model returned a non-object JSON value: {type(data).__name__}")
    return data
