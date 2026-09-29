"""Demo Data Seeder — Idempotent seeding for demo tenders, requirements, and bidders.

Used on serverless/fresh database startups so that demo dashboards show real evaluation counts out-of-the-box.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy.orm import Session

from app.audit import audit
from app.db.models import AuditEvent, Bidder, Requirement, Tender

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parent / "config" / "rules_config.json"
TENDER_REF = "GEM/2026/T/50001"
BIDDER_KEYS = ["A", "B", "C"]
BIDDER_NAMES = {
    "A": "Bidder A: ABC Technologies Pvt Ltd",
    "B": "Bidder B: ABC Technologies Pvt Ltd",
    "C": "Bidder C: ABC Technologies Pvt Ltd",
}

DEMO_PROFILES = {
    "A": {
        "score": 92.0,
        "risk": "LOW",
        "recommendation": "APPROVE",
        "critical_override_fired": False,
        "manual_review": False,
        "rule_results": [],
    },
    "B": {
        "score": 45.0,
        "risk": "HIGH",
        "recommendation": "REJECT",
        "critical_override_fired": True,
        "manual_review": True,
        "rule_results": [],
    },
    "C": {
        "score": 68.0,
        "risk": "MEDIUM",
        "recommendation": "SEND_FOR_CLARIFICATION",
        "critical_override_fired": False,
        "manual_review": True,
        "rule_results": [],
    },
}

DEMO_IDENTITY = {
    "A": {"verdict": "SATISFIED", "outliers": [], "missing": []},
    "B": {"verdict": "VIOLATION", "outliers": ["UDYAM"], "missing": ["UDYAM"]},
    "C": {"verdict": "CONFLICT", "outliers": ["UDYAM"], "missing": []},
}


def _load_rules_config() -> dict:
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open(encoding="utf-8") as fh:
            return json.load(fh)
    return {"rules": []}


def seed_demo_data(db: Session) -> None:
    """Idempotently seed demo tender, requirements, bidders, and summary profiles."""
    existing_tender = db.query(Tender).filter_by(tender_ref=TENDER_REF).first()
    if existing_tender:
        logger.info("Demo tender %s already exists — skipping seed.", TENDER_REF)
        return

    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        config = _load_rules_config()
    except Exception as exc:
        logger.warning("Could not load rules_config.json for seeding: %s", exc)
        config = {"rules": []}

    tender = Tender(
        id=uuid.uuid4(),
        tender_ref=TENDER_REF,
        title="Phase 5 Rule Engine Seed Tender",
        minimum_turnover=5.0,
        required_msme_tier=None,
        local_content_requirement_applicable=True,
        required_local_content_class="class_2_local_supplier",
        bid_value_cr=80.0,
        required_oem=None,
    )
    db.add(tender)
    db.flush()

    for index, rule in enumerate(config.get("rules", []), start=1):
        db.add(
            Requirement(
                id=uuid.uuid4(),
                tender_id=tender.id,
                requirement_id=f"REQ-{index:03}",
                title=rule.get("requirement", f"Rule {index}"),
                category=rule.get("category", "GENERAL"),
                required_evidence=[],
                rule_id=rule.get("rule_id", f"RULE-{index:03}"),
                status="PENDING",
            )
        )

    audit(
        db,
        "TENDER_UPLOADED",
        tender_id=tender.id,
        detail={"tender_ref": TENDER_REF, "title": tender.title},
    )

    for key in BIDDER_KEYS:
        name = BIDDER_NAMES[key]
        summary = {
            "evaluated_at": now_iso,
            "entity_consistency": DEMO_IDENTITY[key],
            "profile": DEMO_PROFILES[key],
        }
        bidder = Bidder(
            id=uuid.uuid4(),
            tender_id=tender.id,
            name=name,
            legal_name="ABC Technologies Pvt Ltd",
            summary=summary,
        )
        db.add(bidder)
        db.flush()

        audit(
            db,
            "BIDDER_CREATED",
            tender_id=tender.id,
            bidder_id=bidder.id,
            detail={"name": name, "key": key},
        )
        audit(
            db,
            "RULES_EVALUATED",
            tender_id=tender.id,
            bidder_id=bidder.id,
            detail={"score": DEMO_PROFILES[key]["score"], "risk": DEMO_PROFILES[key]["risk"]},
        )

    db.commit()
    logger.info("Successfully seeded demo tender %s and bidders A, B, C.", TENDER_REF)
