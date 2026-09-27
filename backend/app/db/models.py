import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums (mirror app.schemas.enums but for SA Column types)
# ---------------------------------------------------------------------------

class Verdict(str, enum.Enum):
    SATISFIED = "SATISFIED"
    VIOLATION = "VIOLATION"
    NOT_VERIFIED = "NOT_VERIFIED"
    CONFLICT = "CONFLICT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class RiskLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class DecisionType(str, enum.Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    SEND_FOR_CLARIFICATION = "SEND_FOR_CLARIFICATION"


class OfficerRole(str, enum.Enum):
    ADMIN = "ADMIN"
    INSPECTOR = "INSPECTOR"
    VIEWER = "VIEWER"


# ---------------------------------------------------------------------------
# Helpers (functions return fresh Column instances per table)
# ---------------------------------------------------------------------------

def _uuid_pk():
    return Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

def _created_at():
    return Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


# ---------------------------------------------------------------------------
# Officer (demo PO account — authentication only, no RBAC model)
# ---------------------------------------------------------------------------

class Officer(Base):
    __tablename__ = "officers"

    id = _uuid_pk()
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(SAEnum(OfficerRole, name="officer_role"), nullable=False, default=OfficerRole.VIEWER)
    created_at = _created_at()


# ---------------------------------------------------------------------------
# Tender + requirements
# ---------------------------------------------------------------------------

class Tender(Base):
    __tablename__ = "tenders"

    id = _uuid_pk()
    tender_ref = Column(String, unique=True, nullable=False, index=True)  # e.g. GEM/2026/T/00456
    title = Column(String, nullable=False)
    uploaded_pdf_path = Column(Text, nullable=True)
    # ponytail: thresholds are tender-level, never in rules_config.json —
    # tender_override_allowed rules re-read these at evaluation time.
    minimum_turnover = Column(Numeric, nullable=True)          # Rs crore
    required_msme_tier = Column(ARRAY(String), nullable=True)  # ['micro','small']
    local_content_requirement_applicable = Column(Boolean, nullable=False, default=False)
    required_local_content_class = Column(String, nullable=True)  # 'class_1' | 'class_2'
    bid_value_cr = Column(Numeric, nullable=True)
    required_oem = Column(String, nullable=True)
    created_at = _created_at()

    requirements = relationship("Requirement", cascade="all, delete-orphan")


class Requirement(Base):
    __tablename__ = "requirements"

    id = _uuid_pk()
    tender_id = Column(UUID(as_uuid=True), ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False, index=True)
    requirement_id = Column(String, nullable=False)            # REQ-001
    title = Column(String, nullable=False)
    category = Column(String, nullable=False)
    source_clause = Column(String, nullable=True)              # "Clause 4.2"
    required_evidence = Column(ARRAY(String), nullable=False, default=list)
    # rule_id references rule_id in app/config/rules_config.json — this table
    # only maps tender clauses to an existing rule; it never defines logic.
    rule_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="PENDING")
    created_at = _created_at()

    rule_results = relationship("RuleResult", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# Bidder + documents + evidence
# ---------------------------------------------------------------------------

class Bidder(Base):
    __tablename__ = "bidders"

    id = _uuid_pk()
    tender_id = Column(UUID(as_uuid=True), ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False, index=True)
    legal_name = Column(String, nullable=True)
    # compliance_score / risk_level / recommendation / manual_review — stored
    # after evaluation so report export never recomputes the analysis.
    summary = Column(JSONB, nullable=False, default=dict)
    created_at = _created_at()
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    documents = relationship("Document", cascade="all, delete-orphan")
    verifications = relationship("Verification", cascade="all, delete-orphan")
    rule_results = relationship("RuleResult", cascade="all, delete-orphan")
    decisions = relationship("Decision", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"

    id = _uuid_pk()
    bidder_id = Column(UUID(as_uuid=True), ForeignKey("bidders.id", ondelete="CASCADE"), nullable=False, index=True)
    tender_id = Column(UUID(as_uuid=True), ForeignKey("tenders.id", ondelete="SET NULL"), nullable=True, index=True)
    doc_type = Column(String, nullable=False, index=True)   # 'PAN' | 'GST' | 'UDYAM'
    file_path = Column(Text, nullable=False)
    uploaded_at = _created_at()
    extraction_method = Column(String, nullable=True)       # 'text_layer' | 'ocr'
    raw_text_excerpt = Column(Text, nullable=True)

    extracted_fields = relationship("ExtractedField", cascade="all, delete-orphan")


class ExtractedField(Base):
    """Evidence object: extracted value + where it came from + confidence."""
    __tablename__ = "extracted_fields"

    id = _uuid_pk()
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    field_name = Column(String, nullable=False, index=True)   # pan, name, gstin, udyam_number...
    value = Column(Text, nullable=True)                        # NULL = not confidently readable
    confidence = Column(Float, nullable=False, default=0.0)
    page = Column(Integer, nullable=True)
    extracted_at = _created_at()


# ---------------------------------------------------------------------------
# Government-source verification (mock adapters behind the adapter interface)
# ---------------------------------------------------------------------------

class Verification(Base):
    __tablename__ = "verifications"

    id = _uuid_pk()
    bidder_id = Column(UUID(as_uuid=True), ForeignKey("bidders.id", ondelete="CASCADE"), nullable=False, index=True)
    source = Column(String, nullable=False, index=True)  # MockGSTAdapter, MockUdyamAdapter...
    identifier = Column(String, nullable=True)
    status = Column(String, nullable=False)              # MATCHED | NOT_FOUND | ERROR
    matched_fields = Column(JSONB, nullable=True)
    confidence = Column(Float, nullable=True)
    response = Column(JSONB, nullable=True)              # full simulated adapter payload
    created_at = _created_at()


# ---------------------------------------------------------------------------
# Rule engine output + officer decision + audit
# ---------------------------------------------------------------------------

class RuleResult(Base):
    __tablename__ = "rule_results"

    id = _uuid_pk()
    bidder_id = Column(UUID(as_uuid=True), ForeignKey("bidders.id", ondelete="CASCADE"), nullable=False, index=True)
    requirement_id = Column(UUID(as_uuid=True), ForeignKey("requirements.id", ondelete="CASCADE"), nullable=False, index=True)
    rule_id = Column(String, nullable=False, index=True)
    verdict = Column(SAEnum(Verdict, name="verdict"), nullable=False, index=True)
    reason = Column(Text, nullable=True)
    # evidence trail refs: [{"extracted_field_id": ..., "document_id": ..., "page": ...}]
    evidence = Column(JSONB, nullable=False, default=list)
    evaluated_at = _created_at()


class Decision(Base):
    __tablename__ = "decisions"

    id = _uuid_pk()
    bidder_id = Column(UUID(as_uuid=True), ForeignKey("bidders.id", ondelete="CASCADE"), nullable=False, index=True)
    decision = Column(SAEnum(DecisionType, name="decision_type"), nullable=False)
    reason = Column(Text, nullable=True)
    officer_id = Column(UUID(as_uuid=True), ForeignKey("officers.id"), nullable=True)
    officer_name = Column(String, nullable=True)  # snapshot — decision stays attributable if officer row changes
    created_at = _created_at()


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = _uuid_pk()
    tender_id = Column(UUID(as_uuid=True), ForeignKey("tenders.id", ondelete="SET NULL"), nullable=True, index=True)
    bidder_id = Column(UUID(as_uuid=True), ForeignKey("bidders.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type = Column(String, nullable=False, index=True)  # TENDER_UPLOADED, RULES_EVALUATED, OFFICER_DECISION...
    actor = Column(String, nullable=False, default="system")  # "system" | officer id/name
    payload = Column(JSONB, nullable=True)
    created_at = _created_at()
