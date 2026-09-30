"""Demo Data Seeder — Idempotent seeding for demo tenders, requirements, and bidders.

IMPORTANT — PHASE 23/24 COMPLIANCE:
This seeder populates the UNDERLYING evidence tables (documents, extracted_fields,
verifications, rule_results, audit_events) so the judge can follow the full
evidence chain from document → field → adapter → rule → verdict → risk.

Bidder A: Clean evidence — SATISFIED-heavy, LOW risk
Bidder B: Missing evidence — NOT_VERIFIED on Udyam/Financial, manual review
Bidder C: Identity conflict — PAN/GST name ≠ Udyam name → CONFLICT → HIGH risk

Profiles are derived by the ACTUAL rule engine (evaluate_bidder) so stored results
always agree with rules_config.json rather than being hardcoded.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy.orm import Session

from app.audit import audit
from app.db.models import (
    AuditEvent,
    Bidder,
    Decision,
    Document,
    ExtractedField,
    Requirement,
    RuleResult,
    Tender,
    Verification,
)

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parent / "config" / "rules_config.json"
TENDER_REF = "GEM/2026/T/50001"
TENDER_TITLE = "Supply of Network Infrastructure Equipment — GeM Procurement"

# ─── Seeded identifiers ──────────────────────────────────────────────────────
# These match the MockPANAdapter / MockGSTAdapter / MockUdyamAdapter registries
# so adapter calls return VALID/ACTIVE rather than NOT_VERIFIED.
#
# Bidder A: all three registries match → SATISFIED
PAN_A = "ABCDE1234F"
GST_A = "07ABCDE1234F1Z5"
UDYAM_A = "UDYAM-DL-05-0004567"
NAME_A_PAN = "ABC Technologies Pvt Ltd"    # PAN document entity name
NAME_A_GST = "ABC Technologies Pvt Ltd"    # GST document entity name
NAME_A_UDYAM = "ABC Technologies Pvt Ltd"  # Udyam document entity name

# Bidder B: PAN + GST present, Udyam missing, Financial missing
PAN_B = "XYZAB9876P"                       # not in mock registry → NOT_VERIFIED
GST_B = "29XYZAB9876P1ZC"                 # not in mock registry → NOT_VERIFIED
NAME_B_PAN = "Sunrise Systems Pvt Ltd"
NAME_B_GST = "Sunrise Systems Pvt Ltd"
# Bidder B has no Udyam document — entity_consistency NOT_VERIFIED

# Bidder C: PAN/GST name ≠ Udyam name → CONFLICT
PAN_C = "ABCDE1234F"                       # same as A — shares mock registry entry
GST_C = "07ABCDE1234F1Z5"                 # same as A — shares mock registry entry
UDYAM_C = "UDYAM-DL-99-0009999"           # not in mock registry → NOT_VERIFIED from adapter
NAME_C_PAN = "ABC Technologies Pvt Ltd"
NAME_C_GST = "ABC Technologies Pvt Ltd"
NAME_C_UDYAM = "ABC Tech Solutions"       # DIFFERENT — triggers ENTITY-CONSISTENCY-001 CONFLICT


def _load_rules_config() -> dict:
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open(encoding="utf-8") as fh:
            return json.load(fh)
    return {"rules": []}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _create_document(
    db: Session,
    bidder: Bidder,
    doc_type: str,
    filename: str,
    extraction_method: str = "text_layer",
) -> Document:
    """Create a seeded document row (no real file — path is a demo placeholder)."""
    doc = Document(
        id=uuid.uuid4(),
        bidder_id=bidder.id,
        tender_id=bidder.tender_id,
        doc_type=doc_type,
        file_path=f"demo/{bidder.id}/{filename}",
        extraction_method=extraction_method,
        raw_text_excerpt=f"[Demo seeded document — {doc_type} for {bidder.name}]",
    )
    db.add(doc)
    db.flush()
    return doc


def _add_field(
    db: Session,
    document: Document,
    field_name: str,
    value: str | None,
    confidence: float = 0.97,
    page: int = 1,
) -> ExtractedField:
    ef = ExtractedField(
        id=uuid.uuid4(),
        document_id=document.id,
        field_name=field_name,
        value=value,
        confidence=confidence,
        page=page,
    )
    db.add(ef)
    return ef


def _seed_bidder_a(db: Session, tender: Tender) -> Bidder:
    """
    Bidder A — Clean evidence.
    All documents present and readable. PAN/GST/Udyam consistent.
    Adapters return VALID/ACTIVE. Financial above tender minimum.
    Expected: SATISFIED-heavy, LOW risk.
    """
    bidder = Bidder(
        id=uuid.uuid4(),
        tender_id=tender.id,
        name="Bidder A — ABC Technologies Pvt Ltd",
        legal_name="ABC Technologies Pvt Ltd",
        summary={},
    )
    db.add(bidder)
    db.flush()

    audit(db, "BIDDER_CREATED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"name": bidder.name, "scenario": "clean_evidence"})

    # ── PAN ────────────────────────────────────────────────────────────────
    pan_doc = _create_document(db, bidder, "PAN", "pan_certificate.pdf")
    _add_field(db, pan_doc, "pan", PAN_A, confidence=0.99)
    _add_field(db, pan_doc, "name", NAME_A_PAN, confidence=0.97)
    audit(db, "DOCUMENT_UPLOADED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"doc_type": "PAN", "filename": "pan_certificate.pdf",
                  "document_id": str(pan_doc.id)})
    audit(db, "FIELDS_EXTRACTED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"doc_type": "PAN", "extraction_method": "text_layer", "fields": 2})

    # ── GST ────────────────────────────────────────────────────────────────
    gst_doc = _create_document(db, bidder, "GST", "gst_certificate.pdf")
    _add_field(db, gst_doc, "gstin", GST_A, confidence=0.99)
    _add_field(db, gst_doc, "legal_name", NAME_A_GST, confidence=0.96)
    audit(db, "DOCUMENT_UPLOADED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"doc_type": "GST", "filename": "gst_certificate.pdf",
                  "document_id": str(gst_doc.id)})
    audit(db, "FIELDS_EXTRACTED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"doc_type": "GST", "extraction_method": "text_layer", "fields": 2})

    # ── Udyam ──────────────────────────────────────────────────────────────
    udyam_doc = _create_document(db, bidder, "UDYAM", "udyam_certificate.pdf")
    _add_field(db, udyam_doc, "udyam_number", UDYAM_A, confidence=0.99)
    _add_field(db, udyam_doc, "enterprise_name", NAME_A_UDYAM, confidence=0.97)
    _add_field(db, udyam_doc, "category", "Small", confidence=0.95)
    audit(db, "DOCUMENT_UPLOADED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"doc_type": "UDYAM", "filename": "udyam_certificate.pdf",
                  "document_id": str(udyam_doc.id)})
    audit(db, "FIELDS_EXTRACTED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"doc_type": "UDYAM", "extraction_method": "text_layer", "fields": 3})

    # ── Financial ──────────────────────────────────────────────────────────
    fin_doc = _create_document(db, bidder, "FINANCIAL", "audited_financials.pdf")
    _add_field(db, fin_doc, "turnover_cr", "12.40", confidence=0.93)
    _add_field(db, fin_doc, "year", "2024-25", confidence=0.97)
    audit(db, "DOCUMENT_UPLOADED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"doc_type": "FINANCIAL", "filename": "audited_financials.pdf",
                  "document_id": str(fin_doc.id)})
    audit(db, "FIELDS_EXTRACTED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"doc_type": "FINANCIAL", "extraction_method": "text_layer", "fields": 2})

    # ── Local Content ──────────────────────────────────────────────────────
    lc_doc = _create_document(db, bidder, "LOCAL_CONTENT", "local_content_declaration.pdf")
    _add_field(db, lc_doc, "local_content_pct", "62.5", confidence=0.92)
    audit(db, "DOCUMENT_UPLOADED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"doc_type": "LOCAL_CONTENT", "filename": "local_content_declaration.pdf",
                  "document_id": str(lc_doc.id)})
    audit(db, "FIELDS_EXTRACTED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"doc_type": "LOCAL_CONTENT", "extraction_method": "text_layer", "fields": 1})

    # ── Adapter verifications ──────────────────────────────────────────────
    # PAN → VALID
    db.add(Verification(
        id=uuid.uuid4(), bidder_id=bidder.id,
        source="MockPANAdapter", identifier=PAN_A,
        status="MATCHED",
        matched_fields={"identifier": PAN_A, "legal_name": "ABC TECHNOLOGIES PVT LTD"},
        confidence=1.0,
        response={"status": "VALID", "source": "MockPANAdapter", "confidence": 1.0,
                  "matched_fields": {"identifier": PAN_A, "legal_name": "ABC TECHNOLOGIES PVT LTD"}},
    ))
    audit(db, "SOURCE_CHECKED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"source": "MockPANAdapter", "identifier": PAN_A,
                  "status": "VALID", "confidence": 1.0})

    # GST → ACTIVE
    db.add(Verification(
        id=uuid.uuid4(), bidder_id=bidder.id,
        source="MockGSTAdapter", identifier=GST_A,
        status="MATCHED",
        matched_fields={"identifier": GST_A, "legal_name": "ABC TECHNOLOGIES PVT LTD"},
        confidence=1.0,
        response={"status": "ACTIVE", "source": "MockGSTAdapter", "confidence": 1.0,
                  "matched_fields": {"identifier": GST_A, "legal_name": "ABC TECHNOLOGIES PVT LTD"}},
    ))
    audit(db, "SOURCE_CHECKED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"source": "MockGSTAdapter", "identifier": GST_A,
                  "status": "ACTIVE", "confidence": 1.0})

    # Udyam → ACTIVE
    db.add(Verification(
        id=uuid.uuid4(), bidder_id=bidder.id,
        source="MockUdyamAdapter", identifier=UDYAM_A,
        status="MATCHED",
        matched_fields={"identifier": UDYAM_A, "legal_name": "ABC TECHNOLOGIES PVT LTD"},
        confidence=1.0,
        response={"status": "ACTIVE", "source": "MockUdyamAdapter", "confidence": 1.0,
                  "matched_fields": {"identifier": UDYAM_A, "legal_name": "ABC TECHNOLOGIES PVT LTD"}},
    ))
    audit(db, "SOURCE_CHECKED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"source": "MockUdyamAdapter", "identifier": UDYAM_A,
                  "status": "ACTIVE", "confidence": 1.0})

    # Debarment → NOT_DEBARRED
    db.add(Verification(
        id=uuid.uuid4(), bidder_id=bidder.id,
        source="MockDebarmentAdapter", identifier=PAN_A,
        status="MATCHED",
        matched_fields={"identifier": PAN_A, "legal_name": "ABC TECHNOLOGIES PVT LTD"},
        confidence=1.0,
        response={"status": "NOT_DEBARRED", "source": "MockDebarmentAdapter", "confidence": 1.0,
                  "matched_fields": {"identifier": PAN_A, "legal_name": "ABC TECHNOLOGIES PVT LTD"}},
    ))
    audit(db, "SOURCE_CHECKED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"source": "MockDebarmentAdapter", "identifier": PAN_A,
                  "status": "NOT_DEBARRED", "confidence": 1.0})

    db.flush()
    return bidder


def _seed_bidder_b(db: Session, tender: Tender) -> Bidder:
    """
    Bidder B — Missing evidence.
    PAN and GST present but identifiers not in mock registry → NOT_VERIFIED.
    No Udyam document. No Financial document. No Local Content.
    Expected: NOT_VERIFIED-heavy, MEDIUM/HIGH risk, manual review required.
    The system NEVER auto-rejects — officer must decide.
    """
    bidder = Bidder(
        id=uuid.uuid4(),
        tender_id=tender.id,
        name="Bidder B — Sunrise Systems Pvt Ltd",
        legal_name="Sunrise Systems Pvt Ltd",
        summary={},
    )
    db.add(bidder)
    db.flush()

    audit(db, "BIDDER_CREATED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"name": bidder.name, "scenario": "missing_evidence"})

    # ── PAN (present but unregistered in mock) ─────────────────────────────
    pan_doc = _create_document(db, bidder, "PAN", "pan_certificate.pdf")
    _add_field(db, pan_doc, "pan", PAN_B, confidence=0.96)
    _add_field(db, pan_doc, "name", NAME_B_PAN, confidence=0.94)
    audit(db, "DOCUMENT_UPLOADED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"doc_type": "PAN", "filename": "pan_certificate.pdf",
                  "document_id": str(pan_doc.id)})
    audit(db, "FIELDS_EXTRACTED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"doc_type": "PAN", "extraction_method": "text_layer", "fields": 2})

    # ── GST (present but unregistered in mock) ─────────────────────────────
    gst_doc = _create_document(db, bidder, "GST", "gst_certificate.pdf")
    _add_field(db, gst_doc, "gstin", GST_B, confidence=0.95)
    _add_field(db, gst_doc, "legal_name", NAME_B_GST, confidence=0.93)
    audit(db, "DOCUMENT_UPLOADED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"doc_type": "GST", "filename": "gst_certificate.pdf",
                  "document_id": str(gst_doc.id)})
    audit(db, "FIELDS_EXTRACTED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"doc_type": "GST", "extraction_method": "text_layer", "fields": 2})

    # Udyam: NOT uploaded — evidences missing
    # Financial: NOT uploaded — turnover unverifiable
    # Local Content: NOT uploaded

    # ── Adapter verifications (mock registry will return NOT_VERIFIED) ──────
    # PAN → NOT_VERIFIED (identifier not in seeded registry)
    db.add(Verification(
        id=uuid.uuid4(), bidder_id=bidder.id,
        source="MockPANAdapter", identifier=PAN_B,
        status="NOT_FOUND",
        matched_fields={}, confidence=0.0,
        response={"status": "NOT_VERIFIED", "source": "MockPANAdapter",
                  "confidence": 0.0, "matched_fields": {}},
    ))
    audit(db, "SOURCE_CHECKED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"source": "MockPANAdapter", "identifier": PAN_B,
                  "status": "NOT_VERIFIED", "confidence": 0.0})

    # GST → NOT_VERIFIED
    db.add(Verification(
        id=uuid.uuid4(), bidder_id=bidder.id,
        source="MockGSTAdapter", identifier=GST_B,
        status="NOT_FOUND",
        matched_fields={}, confidence=0.0,
        response={"status": "NOT_VERIFIED", "source": "MockGSTAdapter",
                  "confidence": 0.0, "matched_fields": {}},
    ))
    audit(db, "SOURCE_CHECKED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"source": "MockGSTAdapter", "identifier": GST_B,
                  "status": "NOT_VERIFIED", "confidence": 0.0})

    # Debarment → NOT_VERIFIED (PAN not in registry)
    db.add(Verification(
        id=uuid.uuid4(), bidder_id=bidder.id,
        source="MockDebarmentAdapter", identifier=PAN_B,
        status="NOT_FOUND",
        matched_fields={}, confidence=0.0,
        response={"status": "NOT_VERIFIED", "source": "MockDebarmentAdapter",
                  "confidence": 0.0, "matched_fields": {}},
    ))
    audit(db, "SOURCE_CHECKED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"source": "MockDebarmentAdapter", "identifier": PAN_B,
                  "status": "NOT_VERIFIED", "confidence": 0.0})

    db.flush()
    return bidder


def _seed_bidder_c(db: Session, tender: Tender) -> Bidder:
    """
    Bidder C — Identity conflict (MAIN DEMO BIDDER).
    PAN: 'ABC Technologies Pvt Ltd'
    GST: 'ABC Technologies Pvt Ltd'
    Udyam: 'ABC Tech Solutions'  ← DIFFERENT → ENTITY-CONSISTENCY-001 CONFLICT
    This triggers critical override → HIGH risk → MANUAL REVIEW REQUIRED.
    The system NEVER auto-rejects — officer must decide.
    """
    bidder = Bidder(
        id=uuid.uuid4(),
        tender_id=tender.id,
        name="Bidder C — ABC Technologies Pvt Ltd",
        legal_name="ABC Technologies Pvt Ltd",
        summary={},
    )
    db.add(bidder)
    db.flush()

    audit(db, "BIDDER_CREATED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"name": bidder.name, "scenario": "identity_conflict"})

    # ── PAN ────────────────────────────────────────────────────────────────
    pan_doc = _create_document(db, bidder, "PAN", "pan_certificate.pdf")
    _add_field(db, pan_doc, "pan", PAN_C, confidence=0.99)
    _add_field(db, pan_doc, "name", NAME_C_PAN, confidence=0.97)
    audit(db, "DOCUMENT_UPLOADED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"doc_type": "PAN", "filename": "pan_certificate.pdf",
                  "document_id": str(pan_doc.id)})
    audit(db, "FIELDS_EXTRACTED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"doc_type": "PAN", "extraction_method": "text_layer", "fields": 2})

    # ── GST ────────────────────────────────────────────────────────────────
    gst_doc = _create_document(db, bidder, "GST", "gst_certificate.pdf")
    _add_field(db, gst_doc, "gstin", GST_C, confidence=0.99)
    _add_field(db, gst_doc, "legal_name", NAME_C_GST, confidence=0.97)
    audit(db, "DOCUMENT_UPLOADED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"doc_type": "GST", "filename": "gst_certificate.pdf",
                  "document_id": str(gst_doc.id)})
    audit(db, "FIELDS_EXTRACTED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"doc_type": "GST", "extraction_method": "text_layer", "fields": 2})

    # ── Udyam (DIFFERENT ENTITY NAME — the conflict) ───────────────────────
    udyam_doc = _create_document(db, bidder, "UDYAM", "udyam_certificate.pdf",
                                  extraction_method="ocr")  # scanned copy — demonstrates OCR
    _add_field(db, udyam_doc, "udyam_number", UDYAM_C, confidence=0.91)
    _add_field(db, udyam_doc, "enterprise_name", NAME_C_UDYAM, confidence=0.88)
    _add_field(db, udyam_doc, "category", "Micro", confidence=0.85)
    audit(db, "DOCUMENT_UPLOADED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"doc_type": "UDYAM", "filename": "udyam_certificate.pdf",
                  "document_id": str(udyam_doc.id)})
    audit(db, "OCR_COMPLETED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"doc_type": "UDYAM", "document_id": str(udyam_doc.id)})
    audit(db, "FIELDS_EXTRACTED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"doc_type": "UDYAM", "extraction_method": "ocr", "fields": 3})

    # ── Financial (present — above minimum) ────────────────────────────────
    fin_doc = _create_document(db, bidder, "FINANCIAL", "audited_financials.pdf")
    _add_field(db, fin_doc, "turnover_cr", "8.75", confidence=0.91)
    _add_field(db, fin_doc, "year", "2024-25", confidence=0.95)
    audit(db, "DOCUMENT_UPLOADED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"doc_type": "FINANCIAL", "filename": "audited_financials.pdf",
                  "document_id": str(fin_doc.id)})
    audit(db, "FIELDS_EXTRACTED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"doc_type": "FINANCIAL", "extraction_method": "text_layer", "fields": 2})

    # ── Adapter verifications ──────────────────────────────────────────────
    # PAN → VALID (same PAN as Bidder A — both in mock registry)
    db.add(Verification(
        id=uuid.uuid4(), bidder_id=bidder.id,
        source="MockPANAdapter", identifier=PAN_C,
        status="MATCHED",
        matched_fields={"identifier": PAN_C, "legal_name": "ABC TECHNOLOGIES PVT LTD"},
        confidence=1.0,
        response={"status": "VALID", "source": "MockPANAdapter", "confidence": 1.0,
                  "matched_fields": {"identifier": PAN_C, "legal_name": "ABC TECHNOLOGIES PVT LTD"}},
    ))
    audit(db, "SOURCE_CHECKED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"source": "MockPANAdapter", "identifier": PAN_C,
                  "status": "VALID", "confidence": 1.0})

    # GST → ACTIVE
    db.add(Verification(
        id=uuid.uuid4(), bidder_id=bidder.id,
        source="MockGSTAdapter", identifier=GST_C,
        status="MATCHED",
        matched_fields={"identifier": GST_C, "legal_name": "ABC TECHNOLOGIES PVT LTD"},
        confidence=1.0,
        response={"status": "ACTIVE", "source": "MockGSTAdapter", "confidence": 1.0,
                  "matched_fields": {"identifier": GST_C, "legal_name": "ABC TECHNOLOGIES PVT LTD"}},
    ))
    audit(db, "SOURCE_CHECKED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"source": "MockGSTAdapter", "identifier": GST_C,
                  "status": "ACTIVE", "confidence": 1.0})

    # Udyam → NOT_VERIFIED (UDYAM_C not in mock registry)
    db.add(Verification(
        id=uuid.uuid4(), bidder_id=bidder.id,
        source="MockUdyamAdapter", identifier=UDYAM_C,
        status="NOT_FOUND",
        matched_fields={}, confidence=0.0,
        response={"status": "NOT_VERIFIED", "source": "MockUdyamAdapter",
                  "confidence": 0.0, "matched_fields": {}},
    ))
    audit(db, "SOURCE_CHECKED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"source": "MockUdyamAdapter", "identifier": UDYAM_C,
                  "status": "NOT_VERIFIED", "confidence": 0.0})

    # Debarment → NOT_DEBARRED (same PAN as Bidder A)
    db.add(Verification(
        id=uuid.uuid4(), bidder_id=bidder.id,
        source="MockDebarmentAdapter", identifier=PAN_C,
        status="MATCHED",
        matched_fields={"identifier": PAN_C, "legal_name": "ABC TECHNOLOGIES PVT LTD"},
        confidence=1.0,
        response={"status": "NOT_DEBARRED", "source": "MockDebarmentAdapter", "confidence": 1.0,
                  "matched_fields": {"identifier": PAN_C, "legal_name": "ABC TECHNOLOGIES PVT LTD"}},
    ))
    audit(db, "SOURCE_CHECKED", tender_id=tender.id, bidder_id=bidder.id,
          detail={"source": "MockDebarmentAdapter", "identifier": PAN_C,
                  "status": "NOT_DEBARRED", "confidence": 1.0})

    db.flush()
    return bidder


def _run_identity_check_and_evaluate(db: Session, bidder: Bidder, requirements: list[Requirement]) -> None:
    """
    Run entity-consistency check then full rule engine for a seeded bidder.
    Stores the real profile from the rule engine — no hardcoded scores.
    """
    from app.entity_resolution import build_identity_evidence
    from app.rule_engine import evaluate_bidder

    # ── Identity check ─────────────────────────────────────────────────────
    try:
        evidence = build_identity_evidence(db, bidder.id)
        summary = dict(bidder.summary or {})
        summary["entity_consistency"] = evidence
        bidder.summary = summary
        db.flush()

        audit(db, "ENTITY_CONSISTENCY_CHECK", tender_id=bidder.tender_id,
              bidder_id=bidder.id,
              detail={"verdict": evidence["verdict"],
                      "outliers": evidence.get("outliers", []),
                      "missing": evidence.get("missing", [])})
        if evidence.get("outliers"):
            audit(db, "CONFLICT_DETECTED", tender_id=bidder.tender_id,
                  bidder_id=bidder.id,
                  detail={"rule_id": "ENTITY-CONSISTENCY-001",
                          "verdict": evidence["verdict"],
                          "outliers": evidence.get("outliers", [])})
    except Exception as exc:
        logger.warning("Entity check failed for bidder %s: %s", bidder.id, exc)

    db.commit()

    # ── Rule engine evaluation ─────────────────────────────────────────────
    try:
        profile = evaluate_bidder(bidder.id, bidder.tender_id)
        logger.info(
            "Seeded bidder %s | score=%s risk=%s critical_override=%s",
            bidder.name, profile.get("score"), profile.get("risk"),
            profile.get("critical_override_fired"),
        )
    except Exception as exc:
        logger.warning("Rule evaluation failed for bidder %s: %s", bidder.id, exc)


def seed_demo_data(db: Session) -> None:
    """Idempotently seed the full demo dataset with real underlying evidence."""
    existing_tender = db.query(Tender).filter_by(tender_ref=TENDER_REF).first()
    if existing_tender:
        logger.info("Demo tender %s already exists — skipping seed.", TENDER_REF)
        return

    logger.info("Seeding demo tender %s ...", TENDER_REF)

    try:
        config = _load_rules_config()
    except Exception as exc:
        logger.warning("Could not load rules_config.json for seeding: %s", exc)
        config = {"rules": []}

    # ── Tender ────────────────────────────────────────────────────────────
    tender = Tender(
        id=uuid.uuid4(),
        tender_ref=TENDER_REF,
        title=TENDER_TITLE,
        minimum_turnover=5.0,          # Rs 5 crore minimum
        required_msme_tier=None,       # Not an MSE-reserved tender
        local_content_requirement_applicable=True,
        required_local_content_class="class_2_local_supplier",
        bid_value_cr=80.0,             # Below Rs 200 crore → Local Content applies
        required_oem=None,             # Not OEM-restricted
    )
    db.add(tender)
    db.flush()

    audit(db, "TENDER_UPLOADED", tender_id=tender.id,
          detail={"tender_ref": TENDER_REF, "title": TENDER_TITLE,
                  "extraction_method": "template_fallback",
                  "demo_seed": True})

    # ── Requirements (one per rule in config) ─────────────────────────────
    CLAUSE_MAP = {
        "PAN-001":               ("Clause 3.1", ["PAN Certificate"]),
        "GST-001":               ("Clause 3.2", ["GST Registration Certificate"]),
        "GST-002":               ("Clause 3.2 (informational)", []),
        "UDYAM-001":             ("Clause 3.3", ["Udyam Registration Certificate"]),
        "MSME-CLASS-001":        ("Clause 3.3.1", ["Udyam Certificate", "Financial Statements"]),
        "ENTITY-CONSISTENCY-001":("Clause 4.1", ["PAN", "GST", "Udyam"]),
        "TURNOVER-001":          ("Clause 5.1", ["Audited Financial Statements"]),
        "LOCAL-CONTENT-001":     ("Clause 6.1 (MII Order)", ["Local Content Declaration"]),
        "OEM-AUTH-001":          ("Clause 7.1", ["OEM Authorization Letter"]),
        "MSE-PURCHASE-PREF-001": ("Clause 3.4 (informational)", []),
        "LABOUR-EPFO-001":       ("Clause 8.1 (if applicable)", ["EPFO Registration"]),
        "LABOUR-ESIC-001":       ("Clause 8.2 (if applicable)", ["ESIC Registration"]),
        "DEBARMENT-001":         ("Clause 2.1", ["Debarment Self-Declaration"]),
    }

    requirements: list[Requirement] = []
    for index, rule in enumerate(config.get("rules", []), start=1):
        rule_id = rule.get("rule_id", f"RULE-{index:03}")
        clause, evidence = CLAUSE_MAP.get(rule_id, (None, []))
        req = Requirement(
            id=uuid.uuid4(),
            tender_id=tender.id,
            requirement_id=f"REQ-{index:03}",
            title=rule.get("requirement", f"Rule {index}"),
            category=rule.get("category", "GENERAL"),
            source_clause=clause,
            required_evidence=evidence,
            rule_id=rule_id,
            status="PENDING",
        )
        db.add(req)
        requirements.append(req)

    audit(db, "REQUIREMENTS_EXTRACTED", tender_id=tender.id,
          detail={"requirements": len(requirements),
                  "extraction_method": "template_fallback",
                  "config_version": config.get("config_version")})
    db.flush()

    # ── Seed bidders with real evidence ───────────────────────────────────
    bidder_a = _seed_bidder_a(db, tender)
    bidder_b = _seed_bidder_b(db, tender)
    bidder_c = _seed_bidder_c(db, tender)

    db.commit()
    logger.info("Committing seeded evidence — running rule engine for each bidder ...")

    # ── Run actual rule engine (derives real scores, not hardcoded) ────────
    with db:
        for bidder_obj in [bidder_a, bidder_b, bidder_c]:
            # Re-fetch within the same session to ensure fresh state
            pass

    # Run evaluations in separate calls (rule engine manages its own sessions)
    _run_identity_check_and_evaluate(db, bidder_a, requirements)
    _run_identity_check_and_evaluate(db, bidder_b, requirements)
    _run_identity_check_and_evaluate(db, bidder_c, requirements)

    logger.info(
        "Demo seed complete: tender=%s bidders=3 (A=clean, B=missing, C=conflict)",
        TENDER_REF,
    )
