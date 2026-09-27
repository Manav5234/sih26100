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
