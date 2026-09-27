"""ENTITY-CONSISTENCY-001 — cross-document identity resolution (Phase 4).

Implements exactly the `normalization_rules` array of that rule in
app/config/rules_config.json, in that order:

    1. case-fold to lowercase
    2. collapse whitespace
    3. strip punctuation
    4. normalize common legal suffixes

PAN / GST / Udyam entity names are compared ONLY through
normalize_entity_name(); no other comparison path exists.

Verdicts: MATCH / CONFLICT / NOT_VERIFIED (as specified in Phase 4).
Note: rules_config.json says pass -> "SATISFIED" for this rule's final
compliance verdict — flagged for the user; identity check itself reports
MATCH. CONFLICT never auto-rejects (rule `notes`): manual review only.
"""
from __future__ import annotations

import re

from app.db.models import Document

RULE_ID = "ENTITY-CONSISTENCY-001"

# doc_type -> name field used for identity comparison
NAME_FIELDS: dict[str, str] = {"PAN": "name", "GST": "legal_name", "UDYAM": "enterprise_name"}
SOURCES: tuple[str, ...] = tuple(NAME_FIELDS)   # canonical order: PAN, GST, UDYAM

# Legal-suffix table. Keys are already lowercased, whitespace-collapsed and
# punctuation-stripped, so map both spaced and punctuated originals here
# (e.g. "p. ltd" -> key "p ltd"). Longest match at end of string wins, so
# "private limited" never falls through to the "limited" rule.
# Review list for edge cases — add forms here, not in code.
SUFFIX_MAP: dict[str, str] = {
    # Private Limited family (canonical: "pvt ltd")
    "private limited": "pvt ltd",
    "private ltd": "pvt ltd",
    "pvt limited": "pvt ltd",
    "pvt ltd": "pvt ltd",
    "p ltd": "pvt ltd",          # "P. Ltd" / "P Ltd" after punctuation strip
    # Limited / company family (canonical: "ltd" / "co")
    "limited": "ltd",
    "ltd": "ltd",
    "company": "co",
    "co": "co",
    "& co": "co",
    "and co": "co",
    "& company": "co",
    "and company": "co",
    # Partnerships — canonical form is itself
    "llp": "llp",
}


def normalize_entity_name(raw: str | None) -> str | None:
    """Rule steps 1-4, in order. None / empty stays None (missing)."""
    if raw is None:
        return None
    text = raw.strip().lower()                          # 1. case-fold
    text = re.sub(r"\s+", " ", text)                    # 2. collapse whitespace
    text = re.sub(r"[.,]", " ", text)                   # 3. strip punctuation
    text = re.sub(r"\s+", " ", text).strip()            #    (as spaces: "p.ltd" -> "p ltd")
    text = _normalize_suffix(text)                      # 4. legal suffixes
    return text or None


def _normalize_suffix(text: str) -> str:
    tokens = text.split()
    for size in range(min(3, len(tokens)), 0, -1):      # longest suffix first
        key = " ".join(tokens[-size:])
        if key in SUFFIX_MAP:
            return " ".join(tokens[:-size] + SUFFIX_MAP[key].split())
    return text


def compare_entities(pan_name: str | None, gst_name: str | None,
                     udyam_name: str | None) -> dict:
    """Pairwise comparison of the three normalized names.

    Missing name -> its pairs are NOT_VERIFIED (never forced to
    MATCH or CONFLICT). A definite mismatch anywhere is CONFLICT.
    """
    raw = {"PAN": pan_name, "GST": gst_name, "UDYAM": udyam_name}
    norm = {source: normalize_entity_name(value) for source, value in raw.items()}
    missing = [s for s in SOURCES if norm[s] is None]

    pairs = []
    for left, right in (("PAN", "GST"), ("PAN", "UDYAM"), ("GST", "UDYAM")):
        a, b = norm[left], norm[right]
        if a is None or b is None:
            verdict = "NOT_VERIFIED"
        elif a == b:
            verdict = "MATCH"
        else:
            verdict = "CONFLICT"
        pairs.append({"sources": [left, right], "verdict": verdict,
                      "values": {left: a, right: b}})

    conflicts = [p for p in pairs if p["verdict"] == "CONFLICT"]
    # Sources disagreeing with the majority of present names (e.g. Udyam is
    # the odd one out, not "3 names, mismatch"). All-different -> all listed.
    present = {s: v for s, v in norm.items() if v is not None}
    outliers: list[str] = []
    if len(set(present.values())) > 1:
        group_sizes = [list(present.values()).count(v) for v in set(present.values())]
        smallest = min(group_sizes)
        outliers = [s for s, v in present.items()
                    if list(present.values()).count(v) == smallest]

    if conflicts:
        verdict = "CONFLICT"
    elif missing:
        verdict = "NOT_VERIFIED"
    else:
        verdict = "MATCH"

    return {
        "verdict": verdict,
        "normalized_values": norm,
        "missing": missing,
        "outliers": outliers,
        "pairs": pairs,
    }


def build_identity_evidence(db, bidder_id) -> dict:
    """Fetch the three name fields from stored extractions, compare, and
    shape the result as rule evidence: {rule_id, verdict, source_documents,
    normalized_values, page_refs, ...}. Pure DB read — caller stores it."""
    names: dict[str, str] = {}
    refs: dict[str, dict] = {}
    for doc_type, field_name in NAME_FIELDS.items():
        doc = (db.query(Document)
               .filter(Document.bidder_id == bidder_id, Document.doc_type == doc_type)
               .order_by(Document.uploaded_at.desc())
               .first())
        if doc is None:
            continue
        extracted = next((f for f in doc.extracted_fields if f.field_name == field_name), None)
        if extracted is None or not extracted.value:
            continue
        names[doc_type] = extracted.value
        refs[doc_type] = {"document_id": str(doc.id), "page": extracted.page,
                          "confidence": extracted.confidence}

    result = compare_entities(names.get("PAN"), names.get("GST"), names.get("UDYAM"))
    return {
        "rule_id": RULE_ID,
        "verdict": result["verdict"],
        "source_documents": [s for s in SOURCES if s in refs],
        "normalized_values": result["normalized_values"],
        "page_refs": [{"source": s, "field": NAME_FIELDS[s], **refs[s]}
                      for s in SOURCES if s in refs],
        "missing": result["missing"],
        "outliers": result["outliers"],
        "pairs": result["pairs"],
    }
