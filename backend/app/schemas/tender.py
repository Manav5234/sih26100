"""Phase 7.5 read models: tender upload / list / requirements."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class RuleJoin(BaseModel):
    """rules_config.json joined onto a requirement so the UI can show the
    legal source (and the config's last_verified) next to the clause."""
    rule_id: str
    requirement: str | None = None
    source: str | None = None
    description: str | None = None
    last_verified: str | None = None


class RequirementOut(BaseModel):
    id: UUID
    tender_id: UUID
    requirement_id: str          # REQ-001
    title: str
    category: str
    source_clause: str | None = None
    required_evidence: list[str] = []
    rule_id: str
    status: str
    rule: RuleJoin | None = None


class RequirementListResponse(BaseModel):
    tender_id: UUID
    tender_ref: str
    requirements: list[RequirementOut]


class TenderFieldsOut(BaseModel):
    """The six tender-level thresholds from the Phase 2 spec."""
    minimum_turnover: float | None = None
    required_msme_tier: list[str] | None = None
    local_content_requirement_applicable: bool = False
    required_local_content_class: str | None = None
    bid_value_cr: float | None = None
    required_oem: str | None = None


class TenderOut(TenderFieldsOut):
    id: UUID
    tender_ref: str
    title: str
    uploaded_pdf_path: str | None = None
    created_at: datetime
    requirement_count: int = 0


class TenderDetailOut(TenderOut):
    """POST /tenders/upload response — says which extraction path ran."""
    extraction_method: str                      # 'llm' | 'template_fallback'
    requirements: list[RequirementOut] = []


class TenderListResponse(BaseModel):
    tenders: list[TenderOut]
    count: int
