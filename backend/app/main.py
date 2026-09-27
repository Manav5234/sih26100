import logging
import time
import time as _time
from collections import defaultdict
from uuid import UUID, uuid4

from fastapi import (Depends, FastAPI, File, Form, HTTPException, Request,
                      UploadFile)
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.audit import audit
from app.auth import (
    _DUMMY_BCRYPT_HASH,
    create_access_token,
    get_current_officer,
    verify_password,
)
from app.config import settings
from app.database import engine
from app.entity_resolution import build_identity_evidence
from app.db.models import AuditEvent as AuditEventDB
from app.db.models import Bidder as BidderDB
from app.db.models import Decision as DecisionDB
from app.db.models import DecisionType as DecisionTypeDB
from app.db.models import Document as DocumentDB
from app.db.models import ExtractedField as ExtractedFieldDB
from app.db.models import Officer as OfficerDB
from app.db.models import Tender as TenderDB
from app.extraction import DOC_SCHEMAS, KEY_FIELD, extract_document
from app.observability import configure_app_logging, request_id_var
from app.schemas.api import AuthLoginRequest, AuthLoginResponse, AuthOfficer, HealthResponse
from app.schemas.bidder import BidderCreate, BidderOut
from app.schemas.dashboard import (AuditEventOut, BidderAuditResponse,
                                   DashboardEntry, DashboardResponse,
                                   DecisionCreate, DecisionOut)
from app.schemas.document import DocumentListResponse, DocumentOut, ExtractedFieldOut
from app.storage import storage

app = FastAPI(title="SIH26100 Bid Compliance Verification Platform")
configure_app_logging()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

logger = logging.getLogger(__name__)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Expose and bind a request ID for every request and downstream log."""
    supplied_id = request.headers.get("X-Request-ID")
    request_id = supplied_id if supplied_id and len(supplied_id) <= 128 else str(uuid4())
    request.state.request_id = request_id
    token = request_id_var.set(request_id)
    started = time.perf_counter()
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_completed",
            extra={
                "event": "request_completed",
                "stage": "request",
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
            },
        )
        return response
    except Exception:
        logger.exception(
            "request_failed",
            extra={
                "event": "request_failed",
                "stage": "request",
                "method": request.method,
                "path": request.url.path,
            },
        )
        raise
    finally:
        request_id_var.reset(token)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "unhandled_exception",
        extra={"event": "unhandled_exception", "path": request.url.path},
    )
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=500, content={"detail": str(exc)})


# ---------------------------------------------------------------------------
# Rate limiting (in-memory, login endpoint only)
# ---------------------------------------------------------------------------
# ponytail: in-memory dict keyed by client IP. Adequate for single-worker
# dev/demo. Horizontal scaling → Redis or a DB-backed counter.

_LOGIN_RATE_LIMIT = 5       # max attempts per window
_LOGIN_WINDOW_SECONDS = 900  # 15 minutes

_login_attempts: dict[str, list[float]] = defaultdict(list)


def _check_login_rate_limit(ip: str) -> None:
    """Raise 429 if IP has exceeded the login rate limit."""
    now = _time.time()
    cutoff = now - _LOGIN_WINDOW_SECONDS
    _login_attempts[ip] = [t for t in _login_attempts[ip] if t > cutoff]
    if len(_login_attempts[ip]) >= _LOGIN_RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
    _login_attempts[ip].append(now)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
def health_check():
    return HealthResponse(status="ok", service="sih26100-backend")


# ---------------------------------------------------------------------------
# Auth — one seeded Procurement Officer account, no registration system
# ---------------------------------------------------------------------------

@app.post("/auth/login", response_model=AuthLoginResponse)
def login(body: AuthLoginRequest, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    _check_login_rate_limit(client_ip)

    with Session(engine) as db:
        officer = db.query(OfficerDB).filter_by(email=body.email).first()
        # ponytail: always run bcrypt (even for nonexistent emails) to prevent
        # a timing side-channel that reveals which emails are registered.
        password_hash = officer.password_hash if officer else _DUMMY_BCRYPT_HASH
        password_valid = verify_password(body.password, password_hash)
        if not officer or not password_valid:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        token = create_access_token(officer.id, officer.role.value)
        return AuthLoginResponse(
            token=token,
            officer=AuthOfficer(id=officer.id, role=officer.role.value),
        )

# ---------------------------------------------------------------------------
# Bidders + document pipeline (Phase 3: PAN / GST / Udyam)
# ---------------------------------------------------------------------------

# ponytail: Phase 3 scope. Financial / OEM doc types join when their
# extraction schemas are validated the same way.
ALLOWED_DOC_TYPES = set(DOC_SCHEMAS)
MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MB


def _document_out(document: DocumentDB) -> DocumentOut:
    order = {name: i for i, name in enumerate(DOC_SCHEMAS.get(document.doc_type, []))}
    fields = sorted(
        document.extracted_fields,
        key=lambda f: (order.get(f.field_name, 99), f.field_name),
    )
    outs = [
        ExtractedFieldOut(
            field_name=f.field_name,
            value=f.value,
            confidence=f.confidence,
            page=f.page,
            extraction_method=document.extraction_method,
        )
        for f in fields
    ]

    if document.extraction_method is None:
        status = "pending"  # uploaded, extraction not finished/failed
    else:
        key = KEY_FIELD.get(document.doc_type)
        if key:
            key_value = next((o.value for o in outs if o.field_name == key), None)
        else:
            key_value = next((o.value for o in outs if o.value), None)
        status = "present" if key_value else "unreadable"

    return DocumentOut(
        id=document.id,
        doc_type=document.doc_type,
        status=status,
        file_path=document.file_path,
        uploaded_at=document.uploaded_at,
        extraction_method=document.extraction_method,
        fields=outs,
    )


@app.post("/bidders", response_model=BidderOut)
def create_bidder(body: BidderCreate):
    with Session(engine) as db:
        if not db.get(TenderDB, body.tender_id):
            raise HTTPException(status_code=404, detail="Tender not found")
        bidder = BidderDB(tender_id=body.tender_id, name=body.name, legal_name=body.legal_name)
        db.add(bidder)
        db.flush()
        audit(db, "BIDDER_CREATED", tender_id=body.tender_id,
              bidder_id=bidder.id, detail={"name": body.name})
        db.commit()
        db.refresh(bidder)
        return BidderOut(id=bidder.id, tender_id=bidder.tender_id,
                         name=bidder.name, legal_name=bidder.legal_name)


@app.post("/bidders/{bidder_id}/documents", response_model=DocumentOut)
async def upload_document(
    bidder_id: UUID,
    doc_type: str = Form(..., description="PAN | GST | UDYAM"),
    file: UploadFile = File(..., description="PDF document"),
):
    """Upload a bidder document and run the extraction pipeline synchronously.

    Text layer first, OCR fallback for image-only pages, then a schema-strict
    LLM read. Every returned field carries page + confidence + method.
    """
    doc_type = doc_type.upper()
    if doc_type not in ALLOWED_DOC_TYPES:
        raise HTTPException(status_code=400,
                            detail=f"Unsupported doc_type '{doc_type}'. Allowed: {sorted(ALLOWED_DOC_TYPES)}")
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF documents are supported")

    raw = await file.read(MAX_PDF_BYTES + 1)
    if len(raw) > MAX_PDF_BYTES:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    with Session(engine) as db:
        bidder = db.get(BidderDB, bidder_id)
        if not bidder:
            raise HTTPException(status_code=404, detail="Bidder not found")

        file_path = storage.save(str(bidder_id), file.filename or f"{doc_type}.pdf", raw)
        document = DocumentDB(
            bidder_id=bidder_id,
            tender_id=bidder.tender_id,
            doc_type=doc_type,
            file_path=file_path,
        )
        db.add(document)
        db.flush()
        audit(db, "DOCUMENT_UPLOADED", tender_id=bidder.tender_id, bidder_id=bidder_id,
              detail={"doc_type": doc_type, "filename": file.filename,
                      "document_id": str(document.id)})
        db.commit()

        fs_path = storage.get_path(file_path)
        if fs_path is None:
            raise HTTPException(status_code=500, detail="Uploaded file could not be stored")

        try:
            result = extract_document(str(fs_path), doc_type)
        except Exception as exc:
            # Row stays with extraction_method=NULL so GET reports 'pending'.
            raise HTTPException(status_code=422, detail=f"extraction failed: {exc}") from exc

        document.extraction_method = result.method
        document.raw_text_excerpt = result.raw_text_excerpt
        for f in result.fields:
            db.add(ExtractedFieldDB(
                document_id=document.id,
                field_name=f.field_name,
                value=f.value,
                confidence=f.confidence,
                page=f.page,
            ))
        if result.method == "ocr":     # image-only page actually went through OCR
            audit(db, "OCR_COMPLETED", tender_id=bidder.tender_id, bidder_id=bidder_id,
                  detail={"doc_type": doc_type, "document_id": str(document.id)})
        audit(db, "FIELDS_EXTRACTED", tender_id=bidder.tender_id, bidder_id=bidder_id,
              detail={"doc_type": doc_type, "extraction_method": result.method,
                      "fields": len(result.fields)})
        db.commit()
        db.refresh(document)
        return _document_out(document)


@app.get("/bidders/{bidder_id}/documents", response_model=DocumentListResponse)
def list_documents(bidder_id: UUID):
    """Status per doc_type: present | missing | unreadable | pending."""
    with Session(engine) as db:
        bidder = db.get(BidderDB, bidder_id)
        if not bidder:
            raise HTTPException(status_code=404, detail="Bidder not found")

        rows = (
            db.query(DocumentDB)
            .filter(DocumentDB.bidder_id == bidder_id)
            .order_by(DocumentDB.uploaded_at)
            .all()
        )
        latest = {d.doc_type: d for d in rows}  # later uploads win
        doc_types = list(DOC_SCHEMAS) + sorted(set(latest) - set(DOC_SCHEMAS))

        return DocumentListResponse(
            bidder_id=bidder_id,
            documents=[_document_out(latest[dt]) if dt in latest
                       else DocumentOut(doc_type=dt, status="missing")
                       for dt in doc_types],
        )

@app.post("/bidders/{bidder_id}/verify-identity")
def verify_identity(bidder_id: UUID):
    """Run ENTITY-CONSISTENCY-001 (PAN/GST/Udyam entity name match) and store
    the evidence on the bidder's compliance profile.

    Evidence shape: {rule_id, verdict, source_documents, normalized_values,
    page_refs, missing, outliers, pairs} — stored under
    summary.entity_consistency. CONFLICT routes to manual review; it never
    auto-rejects (per the rule's notes)."""
    with Session(engine) as db:
        bidder = db.get(BidderDB, bidder_id)
        if not bidder:
            raise HTTPException(status_code=404, detail="Bidder not found")

        evidence = build_identity_evidence(db, bidder_id)
        summary = dict(bidder.summary or {})
        summary["entity_consistency"] = evidence
        bidder.summary = summary
        audit(db, "ENTITY_CONSISTENCY_CHECK", tender_id=bidder.tender_id,
              bidder_id=bidder_id, detail={"verdict": evidence["verdict"]})
        db.commit()
        return evidence


# ---------------------------------------------------------------------------
# Phase 7: stored submission record -> officer dashboard + audit timeline
# ---------------------------------------------------------------------------

@app.get("/dashboard", response_model=DashboardResponse)
def dashboard():
    """All bidders across tenders, read from bidders.summary.profile — the
    stored submission record. Nothing is re-evaluated on page load."""
    with Session(engine) as db:
        rows = (db.query(BidderDB, TenderDB)
                .join(TenderDB, BidderDB.tender_id == TenderDB.id)
                .order_by(TenderDB.tender_ref, BidderDB.name)
                .all())
        # newest decision wins when a bidder has more than one
        decided = {d.bidder_id: d for d in
                   db.query(DecisionDB).order_by(DecisionDB.created_at.desc()).all()}

        entries = []
        for bidder, tender in rows:
            summary = bidder.summary or {}
            profile = summary.get("profile")
            decision = decided.get(bidder.id)
            if decision is not None:
                status = decision.decision.value
            elif profile is None:
                status = "AWAITING_EVALUATION"
            else:
                status = "AWAITING_DECISION"
            # pending = still needs officer attention: undecided AND (not yet
            # evaluated, or evaluated with the manual-review flag set).
            pending = decision is None and (profile is None
                                            or bool(profile.get("manual_review")))
            entries.append(DashboardEntry(
                bidder_id=bidder.id,
                name=bidder.name,
                tender_id=tender.id,
                tender_ref=tender.tender_ref,
                score=profile.get("score") if profile else None,
                risk=profile.get("risk") if profile else None,
                status=status,
                pending_review=pending,
                recommendation=profile.get("recommendation") if profile else None,
                evaluated_at=summary.get("evaluated_at"),
            ))
        return DashboardResponse(bidders=entries, count=len(entries))


@app.get("/bidders/{bidder_id}/audit", response_model=BidderAuditResponse)
def bidder_audit(bidder_id: UUID):
    """Full audit trail for one bidder in chronological order: the bidder's
    own stages plus the tender-level stages (tender upload, requirements)
    that precede it."""
    with Session(engine) as db:
        bidder = db.get(BidderDB, bidder_id)
        if not bidder:
            raise HTTPException(status_code=404, detail="Bidder not found")
        rows = (db.query(AuditEventDB)
                .filter(or_(AuditEventDB.bidder_id == bidder_id,
                            and_(AuditEventDB.bidder_id.is_(None),
                                 AuditEventDB.tender_id == bidder.tender_id)))
                .order_by(AuditEventDB.created_at.asc())
                .all())
        events = [AuditEventOut(bidder_id=r.bidder_id, tender_id=r.tender_id,
                                stage=r.event_type, detail=r.payload or {},
                                timestamp=r.created_at)
                  for r in rows]
        return BidderAuditResponse(bidder_id=bidder_id, tender_id=bidder.tender_id,
                                   events=events)


@app.post("/bidders/{bidder_id}/decisions", response_model=DecisionOut)
def record_decision(bidder_id: UUID, body: DecisionCreate,
                    officer: OfficerDB = Depends(get_current_officer)):
    """The ONLY final decision in the platform: a Procurement Officer's
    Approve / Reject / Send for Clarification, stored with officer, reason
    and timestamp. The rule engine never calls this."""
    try:
        decision = DecisionTypeDB(body.decision)
    except ValueError:
        raise HTTPException(status_code=400,
                            detail=f"decision must be one of "
                                   f"{[d.value for d in DecisionTypeDB]}") from None
    with Session(engine) as db:
        bidder = db.get(BidderDB, bidder_id)
        if not bidder:
            raise HTTPException(status_code=404, detail="Bidder not found")
        row = DecisionDB(bidder_id=bidder_id, decision=decision,
                         reason=body.reason, officer_id=officer.id,
                         officer_name=officer.name)
        db.add(row)
        db.flush()
        audit(db, "OFFICER_DECISION_RECORDED", tender_id=bidder.tender_id,
              bidder_id=bidder_id, actor=officer.name,
              detail={"decision": decision.value, "reason": body.reason})
        db.commit()
        db.refresh(row)
        return DecisionOut(id=row.id, bidder_id=bidder_id,
                           decision=row.decision.value, reason=row.reason,
                           officer_name=row.officer_name,
                           created_at=row.created_at)