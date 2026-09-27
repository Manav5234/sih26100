"""Phase 6.7: financial / OEM / local-content documents -> rule evidence.

Same Phase 3 contract: pdfplumber/OCR -> LLM structured extraction, null
over guessing; then build_bidder_evidence wires values where the config
conditions read them (bidder block for numerics, authorization root for
the OEM letter)."""
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import extraction
from app.db.models import Base, Bidder, Document, ExtractedField, Requirement, Tender
from app.extraction import extract_document
from app.rule_engine import build_bidder_evidence, evaluate_bidder, load_config

FIXTURES = Path(__file__).parent / "fixtures"


class LLMStub:
    def __init__(self, monkeypatch, response: dict):
        monkeypatch.setattr(extraction.llm, "extract_json",
                            lambda prompt, *, keys, timeout=0: dict(response))


def test_financial_schema_extracts_without_key_format_gate(monkeypatch):
    # "12.40" would be nulled by KEY_FORMATS if a key field were defined —
    # financial values are evidence, not identifiers
    LLMStub(monkeypatch, {"turnover_cr": 12.40, "financial_year": "2024-25",
                          "entity_name": "ABC TECHNOLOGIES PVT LTD"})
    result = extract_document(str(FIXTURES / "sample_financials.pdf"), "FINANCIAL")
    assert result.method == "text_layer"
    by_name = {f.field_name: f for f in result.fields}
    assert by_name["turnover_cr"].value == "12.4"      # numbers round-trip via str(float)
    assert by_name["turnover_cr"].confidence == 0.7


def test_oem_and_local_content_schemas(monkeypatch):
    LLMStub(monkeypatch, {"oem_name": "Siemens",
                          "authorization_statement": "M/s ABC TECHNOLOGIES PVT LTD is authorised.",
                          "entity_name": "ABC TECHNOLOGIES PVT LTD"})
    oem = extract_document(str(FIXTURES / "sample_oem_authorization.pdf"),
                           "OEM_AUTHORIZATION")
    assert {f.field_name for f in oem.fields} == {"oem_name",
                                                  "authorization_statement",
                                                  "entity_name"}
    assert all(f.value for f in oem.fields)

    LLMStub(monkeypatch, {"local_content_pct": "45%", "entity_name": "ABC TECHNOLOGIES PVT LTD"})
    local = extract_document(str(FIXTURES / "sample_local_content.pdf"), "LOCAL_CONTENT")
    by_name = {f.field_name: f for f in local.fields}
    assert by_name["local_content_pct"].value == "45%"


@pytest.fixture
def session():
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def add_doc(session, bidder, doc_type: str, fields: dict) -> Document:
    doc = Document(id=uuid4(), bidder_id=bidder.id, tender_id=bidder.tender_id,
                   doc_type=doc_type, file_path=f"/uploads/{doc_type}.pdf",
                   extraction_method="text_layer")
    session.add(doc)
    session.flush()
    for name, value in fields.items():
        session.add(ExtractedField(id=uuid4(), document_id=doc.id,
                                   field_name=name, value=value,
                                   confidence=1.0, page=1))
    return doc


def test_evidence_wiring_for_phase67_documents(session):
    bidder = Bidder(id=uuid4(), tender_id=uuid4(), name="A",
                    legal_name="ABC Technologies Pvt Ltd", summary={})
    session.add(bidder)
    session.flush()
    add_doc(session, bidder, "FINANCIAL",
            {"turnover_cr": "12.40", "financial_year": "2024-25",
             "entity_name": "ABC TECHNOLOGIES PVT LTD"})
    add_doc(session, bidder, "OEM_AUTHORIZATION",
            {"oem_name": "Siemens",
             "authorization_statement": "authorised channel partner",
             "entity_name": "ABC TECHNOLOGIES PVT LTD"})
    add_doc(session, bidder, "LOCAL_CONTENT",
            {"local_content_pct": "45%", "entity_name": "ABC TECHNOLOGIES PVT LTD"})
    session.commit()

    ev = build_bidder_evidence(session, bidder)
    assert ev["bidder"]["turnover"] == 12.4            # parsed, not "12.40"
    assert ev["bidder"]["local_content_pct"] == 45.0   # '45%' -> 45.0
    assert ev["authorization"]["present"] is True
    assert ev["authorization"]["oem_name"] == "Siemens"
    assert ev["_refs"]["bidder.turnover"]["doc_type"] == "FINANCIAL"
    assert ev["_refs"]["bidder.local_content_pct"]["origin"] == "document"
    assert ev["_refs"]["authorization.present"]["origin"] == "derived"


def test_missing_phase67_documents_leave_rules_unverifiable(session):
    # Bidder B: only identity docs -> no numerics, no authorization block
    bidder = Bidder(id=uuid4(), tender_id=uuid4(), name="B",
                    legal_name="ABC Technologies Pvt Ltd", summary={})
    session.add(bidder)
    session.flush()
    add_doc(session, bidder, "PAN", {"pan": "ABCDE1234F", "name": "ABC TECHNOLOGIES PVT LTD"})
    session.commit()

    ev = build_bidder_evidence(session, bidder)
    assert "turnover" not in ev["bidder"]
    assert "local_content_pct" not in ev["bidder"]
    assert "authorization" not in ev


def test_unparseable_numbers_stay_null(session):
    bidder = Bidder(id=uuid4(), tender_id=uuid4(), name="X",
                    legal_name="ABC", summary={})
    session.add(bidder)
    session.flush()
    add_doc(session, bidder, "FINANCIAL", {"turnover_cr": "Rs. 12 crore",
                                           "entity_name": "ABC"})
    session.commit()
    ev = build_bidder_evidence(session, bidder)
    assert "turnover" not in ev["bidder"]              # null over guessing


def test_clean_bidder_full_profile_hits_low_risk(session, monkeypatch):
    """Bidder A's demo claim as a unit: every non-deferred rule evaluable,
    score 90 >= 85 -> LOW risk, no manual review."""
    tender = Tender(id=uuid4(), tender_ref="GEM/2026/T/50001",
                    title="Phase 6.7 profile", minimum_turnover=5.0,
                    required_msme_tier=None,
                    local_content_requirement_applicable=True,
                    bid_value_cr=80.0,
                    required_local_content_class="class_2_local_supplier",
                    required_oem=None)
    bidder = Bidder(id=uuid4(), tender_id=tender.id, name="A",
                    legal_name="ABC Technologies Pvt Ltd",
                    summary={"entity_consistency": {
                        "verdict": "MATCH", "page_refs": [],
                        "outliers": [], "missing": []}})
    session.add_all([tender, bidder])
    session.flush()
    for index, rule in enumerate(load_config()["rules"], start=1):
        session.add(Requirement(id=uuid4(), tender_id=tender.id,
                                requirement_id=f"REQ-{index:03}",
                                title=rule["requirement"], category=rule["category"],
                                required_evidence=[], rule_id=rule["rule_id"],
                                status="PENDING"))
    add_doc(session, bidder, "PAN",
            {"pan": "ABCDE1234F", "name": "ABC TECHNOLOGIES PVT LTD"})
    add_doc(session, bidder, "GST",
            {"gstin": "07ABCDE1234F1Z5", "legal_name": "ABC TECHNOLOGIES PVT LTD",
             "status": "Active"})
    add_doc(session, bidder, "UDYAM",
            {"udyam_number": "UDYAM-DL-05-0004567",
             "enterprise_name": "ABC TECHNOLOGIES PVT LTD", "category": "Micro"})
    add_doc(session, bidder, "FINANCIAL",
            {"turnover_cr": "12.40", "financial_year": "2024-25",
             "entity_name": "ABC TECHNOLOGIES PVT LTD"})
    add_doc(session, bidder, "OEM_AUTHORIZATION",
            {"oem_name": "Siemens",
             "authorization_statement": "authorised channel partner",
             "entity_name": "ABC TECHNOLOGIES PVT LTD"})
    add_doc(session, bidder, "LOCAL_CONTENT",
            {"local_content_pct": "45%", "entity_name": "ABC TECHNOLOGIES PVT LTD"})
    session.commit()

    monkeypatch.setattr("app.rule_engine.engine", session.get_bind())
    profile = evaluate_bidder(bidder.id, tender.id)
    verdicts = {r["rule_id"]: r["verdict"] for r in profile["rule_results"]}

    for rule_id in ("TURNOVER-001", "OEM-AUTH-001", "LOCAL-CONTENT-001",
                    "UDYAM-001", "PAN-001", "GST-001", "DEBARMENT-001",
                    "ENTITY-CONSISTENCY-001"):
        assert verdicts[rule_id] == "SATISFIED", (rule_id, verdicts[rule_id])
    assert verdicts["LABOUR-EPFO-001"] == "NOT_VERIFIED"    # employee_count deferred
    assert verdicts["LABOUR-ESIC-001"] == "NOT_VERIFIED"
    assert verdicts["MSME-CLASS-001"] == "NOT_APPLICABLE"    # tier unspecified

    assert profile["score"] == 90           # (8*1.0 + 2*0.5) / 10 evaluated
    assert profile["risk"] == "LOW"
    assert profile["critical_override_fired"] is False
    assert profile["manual_review"] is False
