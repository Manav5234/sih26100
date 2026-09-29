import logging
import time
import time as _time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from fastapi import (Depends, FastAPI, File, Form, HTTPException, Request,
                      UploadFile)
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import and_, or_
from sqlalchemy.engine import make_url
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
from app.entity_resolution import (SOURCES, build_identity_evidence,
                                   fetch_identity_names, normalize_entity_name)
from app.db.models import AuditEvent as AuditEventDB
from app.db.models import Bidder as BidderDB
from app.db.models import Decision as DecisionDB
from app.db.models import DecisionType as DecisionTypeDB
from app.db.models import Document as DocumentDB
from app.db.models import ExtractedField as ExtractedFieldDB
from app.db.models import Officer as OfficerDB
from app.db.models import Requirement as RequirementDB
from app.db.models import Tender as TenderDB
from app.extraction import DOC_SCHEMAS, KEY_FIELD, extract_document, read_pages
from app.observability import configure_app_logging, request_id_var
from app.rule_engine import _tender_dict, evaluate_bidder, load_config
from app.schemas.api import AuthLoginRequest, AuthLoginResponse, AuthOfficer, HealthResponse
from app.schemas.bidder import BidderCreate, BidderOut
from app.schemas.dashboard import (AuditEventOut, BidderAuditResponse,
                                   ComplianceProfileOut, DashboardEntry,
                                   DashboardResponse, DecisionCreate,
                                   DecisionOut, ProfileRuleResult)
from app.schemas.document import DocumentListResponse, DocumentOut, ExtractedFieldOut
from app.schemas.tender import (RequirementListResponse, RequirementOut,
                                RuleJoin, TenderDetailOut, TenderListResponse,
                                TenderOut)
from app.storage import storage
from app.tender_extraction import extract_tender


logger = logging.getLogger(__name__)


def startup_health_check() -> None:
    """Boot-time orientation, logged once: which database this process is
    pointed at (password masked) and whether the LLM answers. Warn only —
    never blocks or crashes startup, so a dead Ollama shows up here as the
    reason a later extraction reports template_fallback."""
    try:
        target = make_url(settings.database_url).render_as_string(hide_password=True)
    except Exception:
        target = "<unparseable DATABASE_URL — check backend/.env>"
    logger.info("startup database_url=%s", target)

    try:
        resp = httpx.get(f"{settings.llm_base_url}/api/tags", timeout=2.0)
        resp.raise_for_status()
        models = [m.get("name", "") for m in resp.json().get("models", [])]
        present = any(m.split(":")[0] == settings.llm_model for m in models)
        if present:
            logger.info("startup llm endpoint=%s reachable model=%s loaded",
                        settings.llm_base_url, settings.llm_model)
        else:
            logger.warning(
                "startup llm endpoint=%s reachable but model %r is not loaded "
                "(available: %s) — extraction will fall back to template_fallback",
                settings.llm_base_url, settings.llm_model,
                ", ".join(models[:10]) or "none")
    except Exception as exc:
        logger.warning(
            "startup llm endpoint=%s unreachable (%s: %s) — extraction will "
            "fall back to template_fallback",
            settings.llm_base_url, type(exc).__name__, exc)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    startup_health_check()
    yield


app = FastAPI(title="SIH26100 Bid Compliance Verification Platform",
              lifespan=lifespan)
configure_app_logging()


@app.middleware("http")
async def strip_api_prefix_middleware(request: Request, call_next):
    """Strip /backend-api or /api prefix when requests are routed via Vercel rewrites."""
    path = request.url.path
    if path.startswith("/backend-api/"):
        request.scope["path"] = path[12:]
    elif path.startswith("/api/"):
        request.scope["path"] = path[4:]
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


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
@app.post("/api/auth/login", response_model=AuthLoginResponse)
def login(body: AuthLoginRequest, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    _check_login_rate_limit(client_ip)

    with Session(engine) as db:
        officer = db.query(OfficerDB).filter(OfficerDB.email.ilike(body.email.strip().lower())).first()
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
# Phase 7.5: tender upload (LLM extraction + template fallback) + reads
# ---------------------------------------------------------------------------

# Every compliance-profile response carries this so the UI cannot forget it.
DEMO_NOTICE = "Demo Environment: government-source results are simulated via mock adapters"


def _rule_join(rule: dict | None, config: dict) -> RuleJoin | None:
    if rule is None:
        return None
    return RuleJoin(rule_id=rule["rule_id"], requirement=rule.get("requirement"),
                    source=rule.get("source"),
                    last_verified=config.get("last_verified"))


def _requirement_out(req: RequirementDB, rules: dict, config: dict) -> RequirementOut:
    return RequirementOut(
        id=req.id, tender_id=req.tender_id, requirement_id=req.requirement_id,
        title=req.title, category=req.category, source_clause=req.source_clause,
        required_evidence=list(req.required_evidence or []),
        rule_id=req.rule_id, status=req.status,
        rule=_rule_join(rules.get(req.rule_id), config),
    )


def _tender_out(tender: TenderDB, config: dict, requirement_count: int) -> TenderOut:
    # _tender_dict converts Numeric -> float and skips id/timestamps, so it is
    # exactly TenderOut's payload minus the three fields added here.
    return TenderOut(id=tender.id, created_at=tender.created_at,
                     requirement_count=requirement_count, **_tender_dict(tender))


def _tender_detail(tender: TenderDB, config: dict,
                   requirements: list[RequirementDB],
                   extraction_method: str) -> TenderDetailOut:
    rules = {r["rule_id"]: r for r in config["rules"]}
    outs = sorted((_requirement_out(r, rules, config) for r in requirements),
                  key=lambda r: r.requirement_id)
    return TenderDetailOut(**_tender_out(tender, config, len(outs)).model_dump(),
                           extraction_method=extraction_method, requirements=outs)


@app.post("/tenders/upload", response_model=TenderDetailOut)
async def upload_tender(
    file: UploadFile = File(..., description="Tender PDF"),
    tender_ref: str | None = Form(None, description="e.g. GEM/2026/T/00456"),
    title: str | None = Form(None),
    officer: OfficerDB = Depends(get_current_officer),
):
    """Ingest a tender PDF: per-page text (text layer, OCR fallback — same
    pipeline as bidder documents), then a schema-strict LLM read of the
    tender_fields + requirements of the Phase 2 spec. Every requirement's
    matches_rule is validated against rules_config.json; invalid ones are
    dropped. If the LLM fails or yields nothing usable, the controlled
    template is stored and extraction_method says "template_fallback".

    Writes TENDER_UPLOADED and REQUIREMENTS_EXTRACTED from this endpoint."""
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF documents are supported")

    raw = await file.read(MAX_PDF_BYTES + 1)
    if len(raw) > MAX_PDF_BYTES:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    config = load_config()
    with Session(engine) as db:
        tender_ref = (tender_ref or "").strip() or f"TENDER-{uuid4().hex[:8].upper()}"
        if db.query(TenderDB).filter_by(tender_ref=tender_ref).first():
            raise HTTPException(status_code=409,
                                detail=f"Tender {tender_ref} already exists")

        tender_id = uuid4()
        file_path = storage.save(str(tender_id), file.filename or "tender.pdf", raw)
        fs_path = storage.get_path(file_path)
        if fs_path is None:
            raise HTTPException(status_code=500, detail="Uploaded file could not be stored")

        try:
            pages = read_pages(str(fs_path))
        except Exception as exc:
            raise HTTPException(status_code=422,
                                detail=f"could not read tender PDF: {exc}") from exc
        text = "\n\n".join(p.text for p in pages if p.text)

        fields, requirements, extraction_method = extract_tender(text, config)
        tender = TenderDB(
            id=tender_id, tender_ref=tender_ref,
            title=(title or "").strip() or (file.filename or "Untitled tender"),
            uploaded_pdf_path=file_path, **fields,
        )
        db.add(tender)
        db.flush()
        rows = []
        for req in requirements:
            row = RequirementDB(id=uuid4(), tender_id=tender_id, status="PENDING", **req)
            db.add(row)
            rows.append(row)

        audit(db, "TENDER_UPLOADED", tender_id=tender_id,
              detail={"tender_ref": tender_ref, "title": tender.title,
                      "filename": file.filename,
                      "extraction_method": extraction_method})
        audit(db, "REQUIREMENTS_EXTRACTED", tender_id=tender_id,
              detail={"requirements": len(rows),
                      "extraction_method": extraction_method,
                      "config_version": config.get("config_version")})
        db.commit()
        db.refresh(tender)
        return _tender_detail(tender, config, rows, extraction_method)


@app.get("/tenders", response_model=TenderListResponse)
def list_tenders():
    config = load_config()
    with Session(engine) as db:
        rows = db.query(TenderDB).order_by(TenderDB.created_at.desc()).all()
        return TenderListResponse(
            tenders=[_tender_out(t, config, len(t.requirements)) for t in rows],
            count=len(rows))


@app.get("/tenders/{tender_id}/requirements", response_model=RequirementListResponse)
def tender_requirements(tender_id: UUID):
    """Requirements joined with the rule's requirement text, legal source and
    the config's last_verified — read straight from rules_config.json."""
    config = load_config()
    rules = {r["rule_id"]: r for r in config["rules"]}
    with Session(engine) as db:
        tender = db.get(TenderDB, tender_id)
        if not tender:
            raise HTTPException(status_code=404, detail="Tender not found")
        reqs = sorted(tender.requirements, key=lambda r: r.requirement_id)
        return RequirementListResponse(
            tender_id=tender.id, tender_ref=tender.tender_ref,
            requirements=[_requirement_out(r, rules, config) for r in reqs])


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


# ---------------------------------------------------------------------------
# Phase 7.5: run the rule engine over the API + read the stored profile
# ---------------------------------------------------------------------------

def _document_filenames(db: Session, bidder_id: UUID) -> dict[str, str]:
    """document_id -> the filename the officer uploaded (DOCUMENT_UPLOADED
    audit payload), falling back to the stored path's basename."""
    names = {str(doc.id): Path(doc.file_path).name
             for doc in db.query(DocumentDB).filter(DocumentDB.bidder_id == bidder_id)}
    for event in (db.query(AuditEventDB)
                  .filter(AuditEventDB.bidder_id == bidder_id,
                          AuditEventDB.event_type == "DOCUMENT_UPLOADED")):
        payload = event.payload or {}
        if payload.get("document_id") and payload.get("filename"):
            names[payload["document_id"]] = payload["filename"]
    return names


def _enrich_refs(refs: list[dict], filenames: dict[str, str]) -> list[dict]:
    """Evidence drawer shape: every ref carries the document filename, the
    extracted value, page, confidence and its source (adapter name for
    registry checks, origin otherwise)."""
    out = []
    for ref in refs or []:
        item = dict(ref)
        document_id = item.get("document_id")
        item["document_filename"] = filenames.get(document_id) if document_id else None
        item.setdefault("source", item.get("origin"))
        out.append(item)
    return out


def _entity_block(rule_id: str, stored: dict | None, names: dict) -> dict | None:
    """ENTITY-CONSISTENCY-001 only: the three names, their normalized forms
    (Phase 4 rules), and which document is the outlier."""
    if rule_id != "ENTITY-CONSISTENCY-001":
        return None
    stored = stored or {}
    normalized = stored.get("normalized_values") or {
        source: normalize_entity_name(value) for source, value in names.items()}
    return {
        "verdict": stored.get("verdict"),
        "names": {source: {"name": names.get(source),
                           "normalized": normalized.get(source)}
                  for source in SOURCES},
        "outliers": stored.get("outliers", []),
        "missing": stored.get("missing", []),
    }


@app.post("/bidders/{bidder_id}/evaluate")
def evaluate_bidder_endpoint(bidder_id: UUID,
                             officer: OfficerDB = Depends(get_current_officer)):
    """Run the rule engine for this bidder against its tender and store the
    profile. Idempotent: re-running replaces rule_results (one set per
    bidder, never appends) and writes exactly one RULES_EVALUATED per run."""
    with Session(engine) as db:
        bidder = db.get(BidderDB, bidder_id)
        if not bidder:
            raise HTTPException(status_code=404, detail="Bidder not found")
        tender_id = bidder.tender_id
    try:
        return evaluate_bidder(bidder_id, tender_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/bidders/{bidder_id}/profile", response_model=ComplianceProfileOut)
def bidder_profile(bidder_id: UUID):
    """Full stored compliance profile for the evidence drawer: score, risk,
    critical override, recommendation, manual review, the officer's decision
    (if any), and every rule result joined with its requirement text, legal
    source and enriched evidence refs."""
    config = load_config()
    rules = {r["rule_id"]: r for r in config["rules"]}
    with Session(engine) as db:
        bidder = db.get(BidderDB, bidder_id)
        if not bidder:
            raise HTTPException(status_code=404, detail="Bidder not found")
        summary = bidder.summary or {}
        profile = summary.get("profile")
        if profile is None:
            raise HTTPException(
                status_code=404,
                detail="No compliance profile stored — run POST /bidders/{id}/evaluate first")

        tender = db.get(TenderDB, bidder.tender_id)
        filenames = _document_filenames(db, bidder_id)
        names, _refs = fetch_identity_names(db, bidder_id)
        identity = summary.get("entity_consistency")

        results = [
            ProfileRuleResult(
                rule_id=result["rule_id"],
                requirement=(rules.get(result["rule_id"]) or {}).get("requirement"),
                verdict=result["verdict"],
                legal_citation=result.get("legal_citation"),
                source=result.get("source", []),
                evidence_refs=_enrich_refs(result.get("evidence_refs"), filenames),
                entity_consistency=_entity_block(result["rule_id"], identity, names),
            )
            for result in profile.get("rule_results", [])
        ]

        decision = (db.query(DecisionDB).filter(DecisionDB.bidder_id == bidder_id)
                    .order_by(DecisionDB.created_at.desc()).first())
        decision_out = (DecisionOut(id=decision.id, bidder_id=bidder_id,
                                    decision=decision.decision.value,
                                    reason=decision.reason,
                                    officer_name=decision.officer_name,
                                    created_at=decision.created_at)
                        if decision else None)

        return ComplianceProfileOut(
            bidder_id=str(bidder_id), tender_id=str(bidder.tender_id),
            tender_ref=tender.tender_ref if tender else None,
            score=profile.get("score"), risk=profile.get("risk"),
            critical_override_fired=bool(profile.get("critical_override_fired")),
            recommendation=profile.get("recommendation"),
            manual_review=bool(profile.get("manual_review")),
            evaluated_at=summary.get("evaluated_at"),
            rule_results=results, decision=decision_out,
            demo_notice=DEMO_NOTICE,
        )
