"""Phase 7 read models: officer dashboard list + per-bidder audit timeline."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class DashboardEntry(BaseModel):
    """One row of the dashboard list view — read from the stored submission
    record (bidders.summary.profile), never recomputed per page load."""
    bidder_id: UUID
    name: str
    tender_id: UUID
    tender_ref: str
    score: int | None = None
    risk: str | None = None
    # AWAITING_EVALUATION | AWAITING_DECISION | APPROVE | REJECT | SEND_FOR_CLARIFICATION
    status: str
    # still needs officer attention: undecided AND (not evaluated, or flagged)
    pending_review: bool
    recommendation: str | None = None
    evaluated_at: datetime | None = None


class DashboardResponse(BaseModel):
    bidders: list[DashboardEntry]
    count: int


class AuditEventOut(BaseModel):
    bidder_id: UUID | None = None
    tender_id: UUID | None = None
    stage: str
    detail: dict[str, Any] = {}
    timestamp: datetime


class BidderAuditResponse(BaseModel):
    bidder_id: UUID
    tender_id: UUID | None = None
    events: list[AuditEventOut]


class DecisionCreate(BaseModel):
    decision: str          # APPROVE | REJECT | SEND_FOR_CLARIFICATION
    reason: str


class DecisionOut(BaseModel):
    id: UUID
    bidder_id: UUID
    decision: str
    reason: str | None = None
    officer_name: str | None = None
    created_at: datetime


class ProfileRuleResult(BaseModel):
    """One rule of the stored compliance profile, joined to its config
    requirement text + legal source, with the evidence drawer's refs."""
    rule_id: str
    requirement: str | None = None
    verdict: str
    legal_citation: str | None = None
    source: list[str] = []
    evidence_refs: list[dict[str, Any]] = []
    # ENTITY-CONSISTENCY-001 only: three names + normalized forms + outlier
    entity_consistency: dict[str, Any] | None = None


class ComplianceProfileOut(BaseModel):
    """GET /bidders/{id}/profile — the stored submission record, read as-is."""
    bidder_id: str
    tender_id: str
    tender_ref: str | None = None
    score: int | None = None
    risk: str | None = None
    critical_override_fired: bool = False
    recommendation: str | None = None
    manual_review: bool = False
    evaluated_at: str | None = None
    rule_results: list[ProfileRuleResult] = []
    decision: DecisionOut | None = None
    demo_notice: str
