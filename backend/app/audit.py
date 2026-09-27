"""Audit trail writes — one row per pipeline stage into audit_events.

Event shape (spec): {bidder_id, tender_id, stage, detail, timestamp}
stored as: event_type = stage, payload = detail, created_at = timestamp.
Tender-level stages carry bidder_id = NULL and are returned in a bidder's
timeline because they belong to that bidder's tender.

Stage vocabulary (append-only, one constant spelling per stage):
    TENDER_UPLOADED          tender created / PDF ingested
    REQUIREMENTS_EXTRACTED   tender clauses mapped to rule_ids
    BIDDER_CREATED           bidder registered against a tender
    DOCUMENT_UPLOADED        bidder PDF stored
    OCR_COMPLETED            an image-only page went through OCR
    FIELDS_EXTRACTED         LLM structured read finished for a document
    SOURCE_CHECKED           one GovernmentSourceAdapter call
    ENTITY_CONSISTENCY_CHECK Phase 4 cross-document name comparison
    RULES_EVALUATED          rule engine produced a compliance profile
    CONFLICT_DETECTED        profile contains VIOLATION / CONFLICT
    OFFICER_DECISION_RECORDED human Approve / Reject / Clarify action

The caller owns the transaction: audit() only queues the row.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import AuditEvent


def audit(
    db: Session,
    stage: str,
    *,
    tender_id: UUID | None = None,
    bidder_id: UUID | None = None,
    detail: dict[str, Any] | None = None,
    actor: str = "system",
) -> None:
    db.add(AuditEvent(
        event_type=stage,
        tender_id=tender_id,
        bidder_id=bidder_id,
        actor=actor,
        payload=detail or {},
    ))
