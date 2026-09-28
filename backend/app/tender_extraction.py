"""Tender intelligence (Phase 2 spec, endpoint-backed in Phase 7.5).

Pipeline: PDF -> read_pages (text layer, OCR fallback — same as bidder docs)
-> LLM strict-JSON read of {tender_fields, requirements} -> validation
against app/config/rules_config.json -> persisted tender + requirements.

The LLM only reads. Every `matches_rule` must be an exact rule_id that
exists in rules_config.json; anything else is dropped, never invented, and a
requirement without a valid rule_id cannot reach the database (Requirement.rule_id
has no NULL path). Null over guessing on every tender field.

Fallback: if the LLM call fails, times out, or yields no usable requirement,
the controlled template (the seeded one-requirement-per-rule set plus the
seed tender's thresholds) is used and extraction_method comes back
"template_fallback" instead of "llm" — the demo never dies on extraction and
the response/audit row still say which path actually ran.
"""
from __future__ import annotations

import logging
import re

from app import llm
from app.rule_engine import _number, load_config

logger = logging.getLogger(__name__)

# Phase 2 tender_fields — the six tender-level thresholds rules re-read at
# evaluation time (tender_override_allowed / not_applicable_when paths).
TENDER_FIELD_KEYS = (
    "minimum_turnover",
    "required_msme_tier",
    "local_content_requirement_applicable",
    "required_local_content_class",
    "bid_value_cr",
    "required_oem",
)

# Controlled fallback = the seeded demo tender (GEM/2026/T/50001) exactly:
# 5.0 cr turnover, 80 cr bid, Make-in-India invoked at class_2, no MSME-tier
# restriction, no named OEM. Honest only because extraction_method says
# "template_fallback" everywhere it is reported.
TEMPLATE_TENDER_FIELDS: dict = {
    "minimum_turnover": 5.0,
    "required_msme_tier": None,
    "local_content_requirement_applicable": True,
    "required_local_content_class": "class_2_local_supplier",
    "bid_value_cr": 80.0,
    "required_oem": None,
}

_MSME_TIERS = ("micro", "small", "medium")


def template_requirements(config: dict) -> list[dict]:
    """The seeded 13-requirement set: one requirement per configured rule,
    in config order, with no clause attribution (nothing was read)."""
    return [
        {"title": rule["requirement"],
         "category": rule["category"],
         "source_clause": None,
         "required_evidence": _evidence_list(rule.get("required_evidence")),
         "rule_id": rule["rule_id"]}
        for rule in config["rules"]
    ]


def extract_tender(text: str, config: dict | None = None) -> tuple[dict, list[dict], str]:
    """(tender_fields, requirements, extraction_method).

    extraction_method is "llm" or "template_fallback" — recorded on the
    response and on the REQUIREMENTS_EXTRACTED audit row.
    """
    config = config or load_config()
    try:
        data = llm.extract_json(_prompt(text, config),
                                keys=["tender_fields", "requirements"])
    except Exception as exc:          # LLMError, httpx errors, timeouts, bad payloads
        logger.warning("tender_llm_failed (%s) -> template_fallback", exc)
        return dict(TEMPLATE_TENDER_FIELDS), _with_ids(template_requirements(config)), "template_fallback"

    fields = _tender_fields(data.get("tender_fields"), config)
    requirements = _requirements(data.get("requirements"), config)
    if not requirements:
        logger.warning("tender_llm_no_valid_requirements -> template_fallback")
        return dict(TEMPLATE_TENDER_FIELDS), _with_ids(template_requirements(config)), "template_fallback"
    if fields["required_oem"] is None:
        _retry_required_oem(text, config, fields)
    return fields, _with_ids(requirements), "llm"


def _with_ids(requirements: list[dict]) -> list[dict]:
    return [dict(req, requirement_id=f"REQ-{index:03}")
            for index, req in enumerate(requirements, start=1)]


# The only OEM names this pipeline can know: whatever the tender text itself
# names after an OEM phrase (rules_config.json carries no OEM registry, so a
# name can only come from the text — nothing is ever invented).
_OEM_PHRASES = (
    r"(?i:OEM\s+authorization\s+letter\s+from)\s+"
    r"([A-Z][\w.&-]*(?:\s+[A-Z][\w.&-]*)*)",
    r"(?i:\bOEM)\s*[:\-]\s*([A-Z][\w.&-]*(?:\s+[A-Z][\w.&-]*)*)",
)


def _oem_in_text(text: str) -> str | None:
    for pattern in _OEM_PHRASES:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    return None


def _retry_required_oem(text: str, config: dict, fields: dict) -> None:
    """One retry, and only when the tender text names an OEM: the model is
    told that name and the answer is kept only if it appears verbatim in the
    text. A missing/null name on both calls leaves required_oem null."""
    candidate = _oem_in_text(text)
    if candidate is None:
        return
    hint = (f"\n\nThe tender text names an OEM: {candidate}. If the tender "
            f"requires an OEM authorization letter from it, set required_oem "
            f"to exactly that name, else null.")
    try:
        data = llm.extract_json(_prompt(text, config) + hint,
                                keys=["tender_fields", "requirements"])
    except Exception as exc:      # one retry must never fail the upload
        logger.warning("tender_oem_retry_failed (%s)", exc)
        return
    raw = data.get("tender_fields")
    value = _text(raw.get("required_oem")) if isinstance(raw, dict) else None
    if value and value.lower() in text.lower():
        fields["required_oem"] = value
    else:
        logger.warning("tender_oem_retry_rejected (%r not in tender text)", value)


def _prompt(text: str, config: dict) -> str:
    rule_ids = ", ".join(rule["rule_id"] for rule in config["rules"])
    class_order = _class_order(config)
    return f"""Extract the tender's eligibility requirements from the tender text below.

Return ONLY valid JSON with exactly these two keys: tender_fields, requirements.

"tender_fields" object with exactly these keys (use null when the tender does not state the value):
- minimum_turnover: minimum annual turnover in Rs crore, plain number (e.g. 5 or 12.40)
- required_msme_tier: list restricted to "micro", "small", "medium", or null when the tender does not restrict by MSME tier
- local_content_requirement_applicable: true only when the tender invokes the
  Make in India / local-content preference; false when it does not
- required_local_content_class: one of {", ".join(class_order)} (or the short form class_1 / class_2), else null
- bid_value_cr: estimated bid value in Rs crore, plain number, else null
- required_oem: the exact OEM/manufacturer name the tender requires authorization
  for, else null when no OEM is named

"requirements": an array of objects, one per eligibility clause you can point
to in the text, each with exactly these keys:
- title: the requirement in one line
- category: e.g. Identity, Tax, MSME, Financial, Local Content, Authorization, Eligibility, Labour Compliance
- source_clause: the clause number exactly as printed (e.g. "Clause 4.2"), else null
- required_evidence: array of evidence document names the bidder must submit (empty array if not stated)
- matches_rule: MUST be copied verbatim from this list: {rule_ids}.
  If no rule in the list applies to a clause, do not include that clause.

Rules: null over guessing — a value that is not fully present in the text is
null; never invent a rule_id; never infer a partially visible number.

Tender text:
{text}"""


def _tender_fields(raw, config: dict) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    applicable = raw.get("local_content_requirement_applicable")
    return {
        "minimum_turnover": _number(raw.get("minimum_turnover")),
        "required_msme_tier": _msme_tiers(raw.get("required_msme_tier"), config),
        # column is NOT NULL: an unstated preference means the tender did not
        # invoke it. The extraction_method on the response still says "llm".
        "local_content_requirement_applicable": applicable if isinstance(applicable, bool) else False,
        "required_local_content_class": _local_content_class(
            raw.get("required_local_content_class"), _class_order(config)),
        "bid_value_cr": _number(raw.get("bid_value_cr")),
        "required_oem": _text(raw.get("required_oem")),
    }


def _msme_tiers(raw, config: dict) -> list[str] | None:
    """Restricted to the tiers MSME-CLASS-001 can actually classify against."""
    rule = next((r for r in config["rules"] if r["rule_id"] == "MSME-CLASS-001"), {})
    allowed = [t for t in rule.get("classification", {}) if t in _MSME_TIERS] or list(_MSME_TIERS)
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return None
    tiers = [t.strip().lower() for t in raw
             if isinstance(t, str) and t.strip().lower() in allowed]
    # de-duplicate, keep the model's order
    tiers = list(dict.fromkeys(tiers))
    return tiers or None


def _class_order(config: dict) -> list[str]:
    rule = next((r for r in config["rules"] if r["rule_id"] == "LOCAL-CONTENT-001"), {})
    return list(rule.get("class_order", []))


def _local_content_class(raw, class_order: list[str]) -> str | None:
    """Only a tier that exists in the rule's class_order survives; 'class_2',
    'Class-2 Local Supplier' etc. normalise onto the config's own spelling."""
    if not isinstance(raw, str) or not class_order:
        return None
    value = re.sub(r"[\s\-]+", "_", raw.strip().lower())
    if value in class_order:
        return value
    return next((c for c in class_order if c.removesuffix("_local_supplier") == value), None)


def _requirements(raw, config: dict) -> list[dict]:
    """Validated rows: invalid / missing / duplicate matches_rule dropped."""
    rules = {rule["rule_id"]: rule for rule in config["rules"]}
    out: list[dict] = []
    seen: set[str] = set()
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        rule_id = item.get("matches_rule")
        if not isinstance(rule_id, str):
            continue
        rule_id = rule_id.strip()
        rule = rules.get(rule_id)               # drop, never invent a rule_id
        if rule is None or rule_id in seen:     # one requirement per rule
            continue
        seen.add(rule_id)
        out.append({
            "title": _text(item.get("title")) or rule["requirement"],
            "category": _text(item.get("category")) or rule["category"],
            "source_clause": _text(item.get("source_clause")),
            # empty from the model -> the rule's own default evidence in
            # rules_config.json (rules carry none today -> stays empty)
            "required_evidence": _evidence_list(item.get("required_evidence"))
            or _evidence_list(rule.get("required_evidence")),
            "rule_id": rule_id,
        })
    return out


def _text(value) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _evidence_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [v.strip() for v in value
            if isinstance(v, str) and v.strip()]
