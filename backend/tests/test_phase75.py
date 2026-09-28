"""Phase 7.5: tender upload API, evaluation endpoint, stored profile read.

Covers the LLM extraction path (mocked) and the forced template fallback,
matches_rule validation against rules_config.json, the audit rows written by
POST /tenders/upload itself, evaluate idempotency, and the evidence-drawer
profile shape (Bidder C: Udyam is the outlier).
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import (AuditEvent, Base, Bidder, Decision, Document,
                           ExtractedField, Officer, OfficerRole, Requirement,
                           RuleResult, Tender)
from app.main import app as fastapi_app
from app.rule_engine import load_config

CONFIG = load_config()
RULES = CONFIG["rules"]
FIXTURES = Path(__file__).resolve().parent / "fixtures"

DEMO_NOTICE = ("Demo Environment: government-source results are simulated "
               "via mock adapters")


@pytest.fixture
def engine():
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine):
    return sessionmaker(bind=engine)()


@pytest.fixture
def token(session):
    officer = Officer(id=uuid4(), name="Priya Sharma",
                      email="priya@example.gov.in",
                      password_hash="x", role=OfficerRole.INSPECTOR)
    session.add(officer)
    session.commit()
    from app.auth import create_access_token
    return create_access_token(officer.id, officer.role.value)


@pytest.fixture
def client(engine, session, token, monkeypatch, tmp_path):
    """TestClient wired to the in-memory engine + a temp upload root."""
    from app.storage import LocalDiskStorage
    monkeypatch.setattr("app.main.engine", engine)
    monkeypatch.setattr("app.database.engine", engine)   # auth get_db()
    monkeypatch.setattr("app.rule_engine.engine", engine)
    monkeypatch.setattr("app.main.storage", LocalDiskStorage(tmp_path))
    with TestClient(fastapi_app) as test_client:
        test_client.headers.update({"Authorization": f"Bearer {token}"})
        yield test_client


def seed_tender(session, tender_ref="GEM/2026/T/70001"):
    tender = Tender(id=uuid4(), tender_ref=tender_ref, title="Phase 7.5 test",
                    minimum_turnover=5.0, required_msme_tier=None,
                    local_content_requirement_applicable=False,
                    bid_value_cr=None, required_local_content_class=None,
                    required_oem=None)
    session.add(tender)
    session.flush()
    for index, rule in enumerate(RULES, start=1):
        session.add(Requirement(id=uuid4(), tender_id=tender.id,
                                requirement_id=f"REQ-{index:03}",
                                title=rule["requirement"], category=rule["category"],
                                required_evidence=[], rule_id=rule["rule_id"],
                                status="PENDING"))
    session.commit()
    return tender


def add_doc(session, bidder, doc_type, fields, filename=None):
    doc = Document(id=uuid4(), bidder_id=bidder.id, tender_id=bidder.tender_id,
                   doc_type=doc_type, file_path=f"/uploads/{bidder.id}/{doc_type}.pdf",
                   extraction_method="text_layer")
    session.add(doc)
    session.flush()
    for name, value in fields.items():
        session.add(ExtractedField(id=uuid4(), document_id=doc.id,
                                   field_name=name, value=value,
                                   confidence=0.9, page=1))
    # what POST /bidders/{id}/documents writes — the profile's filename lookup
    session.add(AuditEvent(id=uuid4(), event_type="DOCUMENT_UPLOADED",
                           tender_id=bidder.tender_id, bidder_id=bidder.id,
                           payload={"doc_type": doc_type,
                                    "filename": filename or f"{doc_type.lower()}.pdf",
                                    "document_id": str(doc.id)}))
    session.commit()
    return doc


def tender_payload():
    return {
        "tender_fields": {
            "minimum_turnover": 5.0,
            "required_msme_tier": ["micro", "not-a-tier"],
            "local_content_requirement_applicable": True,
            "required_local_content_class": "class_2",
            "bid_value_cr": 80,
            "required_oem": "Siemens",
        },
        "requirements": [
            {"title": "Valid PAN", "category": "Identity",
             "source_clause": "Clause 2.1", "required_evidence": ["PAN card copy"],
             "matches_rule": "PAN-001"},
            {"title": "Invented rule", "category": "Identity",
             "source_clause": None, "required_evidence": [],
             "matches_rule": "NOT-A-RULE-999"},          # dropped
            {"title": "No mapping", "category": "Other",
             "source_clause": None, "required_evidence": [],
             "matches_rule": None},                      # dropped
            {"title": "Minimum turnover Rs 5 crore", "category": "Financial",
             "source_clause": "Clause 3.1",
             "required_evidence": ["Audited financial statements"],
             "matches_rule": "TURNOVER-001"},
        ],
    }


def upload(client, **form):
    pdf = (FIXTURES / "sample_tender.pdf").read_bytes()
    return client.post("/tenders/upload",
                       files={"file": ("sample_tender.pdf", pdf, "application/pdf")},
                       data=form)


def audit_stages(session, tender_id):
    return [(r.event_type, r.payload) for r in
            session.query(AuditEvent).filter(AuditEvent.tender_id == tender_id)
            .order_by(AuditEvent.created_at).all()]


# --- 1. POST /tenders/upload, LLM path ---------------------------------------

def test_upload_tender_llm_path_persists_requirements_and_audit(client, session,
                                                                monkeypatch):
    import app.llm
    monkeypatch.setattr(app.llm, "extract_json",
                        lambda *a, **k: tender_payload())

    resp = upload(client, tender_ref="GEM/2026/T/71001",
                  title="Signalling equipment")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["extraction_method"] == "llm"
    assert body["tender_ref"] == "GEM/2026/T/71001"
    assert body["minimum_turnover"] == 5.0
    assert body["bid_value_cr"] == 80.0
    assert body["required_oem"] == "Siemens"
    assert body["local_content_requirement_applicable"] is True
    # class_2 normalises onto the config's own class_order spelling
    assert body["required_local_content_class"] == "class_2_local_supplier"
    assert body["required_msme_tier"] == ["micro"]        # bogus tier dropped

    # invalid matches_rule rows never reach the response or the database
    assert [r["rule_id"] for r in body["requirements"]] == ["PAN-001", "TURNOVER-001"]
    assert [r["requirement_id"] for r in body["requirements"]] == ["REQ-001", "REQ-002"]
    assert not any(r["rule_id"] == "NOT-A-RULE-999" for r in body["requirements"])
    for requirement in body["requirements"]:
        rule = requirement["rule"]
        assert rule["rule_id"] == requirement["rule_id"]
        assert rule["source"] and rule["last_verified"] == CONFIG["last_verified"]
        assert requirement["title"] and requirement["category"]
    assert body["requirements"][0]["source_clause"] == "Clause 2.1"
    assert body["requirements"][0]["required_evidence"] == ["PAN card copy"]

    tender = session.query(Tender).filter_by(tender_ref="GEM/2026/T/71001").one()
    rows = session.query(Requirement).filter_by(tender_id=tender.id).all()
    assert sorted(r.rule_id for r in rows) == ["PAN-001", "TURNOVER-001"]
    assert body["id"] == str(tender.id)
    assert tender.uploaded_pdf_path.endswith(".pdf")

    # audit rows are written by THIS endpoint, with the extraction path
    stages = dict(audit_stages(session, tender.id))
    assert stages["TENDER_UPLOADED"]["extraction_method"] == "llm"
    assert stages["TENDER_UPLOADED"]["tender_ref"] == "GEM/2026/T/71001"
    assert stages["REQUIREMENTS_EXTRACTED"]["requirements"] == 2
    assert stages["REQUIREMENTS_EXTRACTED"]["extraction_method"] == "llm"

    # reads: list + requirements joined with the config rule text/source
    listed = client.get("/tenders").json()
    match = [t for t in listed["tenders"] if t["tender_ref"] == "GEM/2026/T/71001"]
    assert listed["count"] == len(listed["tenders"]) and match
    assert match[0]["requirement_count"] == 2

    joined = client.get(f"/tenders/{tender.id}/requirements").json()
    assert [r["rule_id"] for r in joined["requirements"]] == ["PAN-001", "TURNOVER-001"]
    pan = joined["requirements"][0]
    assert pan["rule"]["requirement"] == RULES[0]["requirement"]
    assert "Income Tax Act" in pan["rule"]["source"]
    assert pan["rule"]["last_verified"] == CONFIG["last_verified"]
    assert client.get(f"/tenders/{uuid4()}/requirements").status_code == 404

    # duplicate ref is refused rather than silently overwriting
    assert upload(client, tender_ref="GEM/2026/T/71001").status_code == 409


# --- 2. forced template fallback ---------------------------------------------

def test_upload_tender_falls_back_to_template_when_llm_fails(client, session,
                                                             monkeypatch):
    import httpx

    def boom(*a, **k):
        raise httpx.ConnectError("ollama is down")

    monkeypatch.setattr("app.llm.extract_json", boom)

    resp = upload(client, tender_ref="GEM/2026/T/71002")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["extraction_method"] == "template_fallback"
    assert len(body["requirements"]) == len(RULES) == 13
    assert [r["rule_id"] for r in body["requirements"]] == \
        [r["rule_id"] for r in RULES]
    assert all(r["source_clause"] is None for r in body["requirements"])
    # seed thresholds keep the demo evaluable on the fallback path
    assert body["minimum_turnover"] == 5.0
    assert body["bid_value_cr"] == 80.0
    assert body["required_local_content_class"] == "class_2_local_supplier"
    assert body["required_msme_tier"] is None

    tender = session.query(Tender).filter_by(tender_ref="GEM/2026/T/71002").one()
    stages = dict(audit_stages(session, tender.id))
    assert stages["TENDER_UPLOADED"]["extraction_method"] == "template_fallback"
    assert stages["REQUIREMENTS_EXTRACTED"]["extraction_method"] == "template_fallback"
    assert stages["REQUIREMENTS_EXTRACTED"]["requirements"] == 13


def test_upload_tender_falls_back_when_every_matches_rule_is_invalid(client, session,
                                                                     monkeypatch):
    import app.llm
    payload = {"tender_fields": {},
               "requirements": [{"title": "Hallucinated", "category": "Other",
                                 "source_clause": None, "required_evidence": [],
                                 "matches_rule": "TOTALLY-MADE-UP-001"}]}
    monkeypatch.setattr(app.llm, "extract_json", lambda *a, **k: payload)

    body = upload(client, tender_ref="GEM/2026/T/71003").json()
    assert body["extraction_method"] == "template_fallback"
    assert len(body["requirements"]) == 13
    tender = session.query(Tender).filter_by(tender_ref="GEM/2026/T/71003").one()
    assert session.query(Requirement).filter_by(tender_id=tender.id).count() == 13


def test_tender_field_coercion_nulls_unparseable():
    from app.tender_extraction import _tender_fields

    fields = _tender_fields({"minimum_turnover": "Rs 5 crore",
                             "bid_value_cr": 80,
                             "required_msme_tier": "small",
                             "local_content_requirement_applicable": "yes",
                             "required_local_content_class": "Class-2 Local Supplier",
                             "required_oem": 7}, CONFIG)
    assert fields["minimum_turnover"] is None      # unparseable -> null, never 5
    assert fields["bid_value_cr"] == 80.0
    assert fields["required_msme_tier"] == ["small"]
    assert fields["local_content_requirement_applicable"] is False
    assert fields["required_local_content_class"] == "class_2_local_supplier"
    assert fields["required_oem"] is None
    assert _tender_fields(None, CONFIG)["minimum_turnover"] is None


# --- 2b. OEM retry + default evidence ---------------------------------------

def llm_payload(oem, evidence=()):
    return {
        "tender_fields": {"minimum_turnover": 5.0, "required_msme_tier": None,
                          "local_content_requirement_applicable": True,
                          "required_local_content_class": "class_2",
                          "bid_value_cr": 80.0, "required_oem": oem},
        "requirements": [{"title": "Valid PAN", "category": "Identity",
                          "source_clause": "Clause 2.1",
                          "required_evidence": list(evidence),
                          "matches_rule": "PAN-001"}],
    }


def test_oem_retry_when_text_names_oem_and_first_call_is_null(monkeypatch):
    from app import llm
    from app.tender_extraction import extract_tender

    prompts: list[str] = []
    replies = [llm_payload(None), llm_payload("Siemens")]

    def fake(prompt, **kwargs):
        prompts.append(prompt)
        return replies[len(prompts) - 1]

    monkeypatch.setattr(llm, "extract_json", fake)
    text = ("The bidder shall hold a valid PAN. Non-OEM bidders shall submit "
            "an OEM authorization letter from Siemens for the products.")
    fields, reqs, method = extract_tender(text, CONFIG)

    assert method == "llm"
    assert len(prompts) == 2                      # exactly one retry
    assert fields["required_oem"] == "Siemens"
    assert "names an OEM: Siemens" in prompts[1]  # retry is told the name
    assert "names an OEM" not in prompts[0]
    assert [r["rule_id"] for r in reqs] == ["PAN-001"]


def test_oem_retry_not_run_when_text_names_no_oem(monkeypatch):
    from app import llm
    from app.tender_extraction import extract_tender

    prompts: list[str] = []

    def fake(prompt, **kwargs):
        prompts.append(prompt)
        return llm_payload(None)

    monkeypatch.setattr(llm, "extract_json", fake)
    fields, _, method = extract_tender("The bidder shall hold a valid PAN.",
                                       CONFIG)
    assert method == "llm"
    assert len(prompts) == 1                      # no retry, no extra call
    assert fields["required_oem"] is None


def test_oem_retry_rejects_a_name_the_text_does_not_contain(monkeypatch):
    from app import llm
    from app.tender_extraction import extract_tender

    replies = [llm_payload(None), llm_payload("Foxconn")]
    calls: list[int] = []

    def fake(prompt, **kwargs):
        calls.append(len(calls))
        return replies[len(calls) - 1]

    monkeypatch.setattr(llm, "extract_json", fake)
    text = ("Non-OEM bidders shall submit an OEM authorization letter from "
            "Siemens for the products.")
    fields, _, method = extract_tender(text, CONFIG)

    assert method == "llm" and len(calls) == 2
    assert fields["required_oem"] is None         # invented name discarded


def test_default_evidence_fills_only_empty_required_evidence(monkeypatch):
    import json

    from app import llm
    from app.tender_extraction import extract_tender, template_requirements

    config = json.loads(json.dumps(CONFIG))       # deep copy of the real file
    config["rules"][0]["required_evidence"] = ["PAN card copy"]
    config["rules"][1]["required_evidence"] = ["GST certificate"]
    payload = dict(llm_payload(None), requirements=[
        {"title": "Valid PAN", "category": "Identity",
         "source_clause": None, "required_evidence": [],
         "matches_rule": "PAN-001"},             # empty -> config default
        {"title": "Valid GST", "category": "Tax",
         "source_clause": "Clause 2.2",
         "required_evidence": ["GST registration certificate"],
         "matches_rule": "GST-001"},             # non-empty -> kept as read
    ])
    monkeypatch.setattr(llm, "extract_json", lambda *a, **k: payload)

    _, reqs, method = extract_tender("The bidder shall hold a valid PAN.",
                                     config)
    assert method == "llm"
    by_rule = {r["rule_id"]: r for r in reqs}
    assert by_rule["PAN-001"]["required_evidence"] == ["PAN card copy"]
    assert by_rule["GST-001"]["required_evidence"] == \
        ["GST registration certificate"]
    # template path reads the same default
    assert template_requirements(config)[0]["required_evidence"] == \
        ["PAN card copy"]


def test_empty_evidence_stays_empty_when_the_rule_has_no_default(monkeypatch):
    """Real rules_config.json shape: rules carry no default evidence, so an
    empty required_evidence from the model stays empty (nothing invented)."""
    from app import llm
    from app.tender_extraction import extract_tender

    assert all("required_evidence" not in rule for rule in RULES)
    monkeypatch.setattr(llm, "extract_json", lambda *a, **k: llm_payload(None))
    _, reqs, method = extract_tender("The bidder shall hold a valid PAN.",
                                     CONFIG)
    assert method == "llm"
    assert reqs[0]["required_evidence"] == []


# --- 3. POST /bidders/{id}/evaluate ------------------------------------------

def test_evaluate_endpoint_is_idempotent(client, session):
    tender = seed_tender(session)
    bidder = Bidder(id=uuid4(), tender_id=tender.id, name="Bidder A",
                    legal_name="ABC Technologies Pvt Ltd", summary={})
    session.add(bidder)
    session.commit()
    add_doc(session, bidder, "GST",
            {"gstin": "07ABCDE1234F1Z5", "legal_name": "ABC TECHNOLOGIES PVT LTD"})

    first = client.post(f"/bidders/{bidder.id}/evaluate")
    assert first.status_code == 200, first.text
    profile = first.json()
    assert profile["score"] is not None and profile["risk"] in ("LOW", "MEDIUM", "HIGH")
    assert len(profile["rule_results"]) == len(RULES)
    assert session.query(RuleResult).filter_by(bidder_id=bidder.id).count() == len(RULES)

    second = client.post(f"/bidders/{bidder.id}/evaluate")
    assert second.status_code == 200
    assert second.json()["score"] == profile["score"]
    # re-evaluation REPLACES rule_results and adds exactly one audit stage
    assert session.query(RuleResult).filter_by(bidder_id=bidder.id).count() == len(RULES)
    evaluated = [name for name, _ in audit_stages(session, tender.id)
                 if name == "RULES_EVALUATED"]
    assert len(evaluated) == 2                      # one per run, no duplicates
    assert session.query(Decision).filter_by(bidder_id=bidder.id).count() == 0

    assert client.post(f"/bidders/{uuid4()}/evaluate").status_code == 404


# --- 4. GET /bidders/{id}/profile --------------------------------------------

def test_profile_shape_for_bidder_c_outlier_is_udyam(client, session):
    tender = seed_tender(session, tender_ref="GEM/2026/T/71004")
    bidder = Bidder(id=uuid4(), tender_id=tender.id,
                    name="Bidder C: ABC Technologies Pvt Ltd",
                    legal_name="ABC Technologies Pvt Ltd", summary={})
    session.add(bidder)
    session.commit()
    add_doc(session, bidder, "PAN", {"pan": "ABCDE1234F",
                                     "name": "ABC TECHNOLOGIES PVT LTD"},
            filename="sample_pan.pdf")
    add_doc(session, bidder, "GST", {"gstin": "07ABCDE1234F1Z5",
                                     "legal_name": "ABC TECHNOLOGIES PVT LTD"},
            filename="sample_gst.pdf")
    add_doc(session, bidder, "UDYAM", {"udyam_number": "UDYAM-DL-05-0004567",
                                       "enterprise_name": "ABC Tech Solutions"},
            filename="sample_udyam_tech_solutions.pdf")

    assert client.post(f"/bidders/{bidder.id}/verify-identity").json()["verdict"] \
        == "CONFLICT"
    assert client.post(f"/bidders/{bidder.id}/evaluate").status_code == 200

    resp = client.get(f"/bidders/{bidder.id}/profile")
    assert resp.status_code == 200, resp.text
    profile = resp.json()

    assert profile["demo_notice"] == DEMO_NOTICE
    assert profile["bidder_id"] == str(bidder.id)
    assert profile["tender_ref"] == "GEM/2026/T/71004"
    assert profile["risk"] == "HIGH" and profile["critical_override_fired"] is True
    assert profile["manual_review"] is True
    assert profile["recommendation"] and profile["evaluated_at"]
    assert profile["decision"] is None

    assert len(profile["rule_results"]) == len(RULES)
    for result in profile["rule_results"]:
        assert result["requirement"]          # joined from rules_config.json
        assert result["verdict"]
        assert result["legal_citation"]       # hard rule 5: legal source
        assert isinstance(result["evidence_refs"], list)
        assert result["entity_consistency"] is None or \
            result["rule_id"] == "ENTITY-CONSISTENCY-001"

    entity = next(r for r in profile["rule_results"]
                  if r["rule_id"] == "ENTITY-CONSISTENCY-001")
    assert entity["verdict"] == "CONFLICT"
    names = entity["entity_consistency"]["names"]
    assert set(names) == {"PAN", "GST", "UDYAM"}
    assert names["PAN"]["normalized"] == "abc technologies pvt ltd"
    assert names["UDYAM"]["normalized"] == "abc tech solutions"
    assert names["PAN"]["name"] == "ABC TECHNOLOGIES PVT LTD"
    assert entity["entity_consistency"]["outliers"] == ["UDYAM"]

    # evidence drawer refs: filename, page, value, confidence, source
    pan = next(r for r in profile["rule_results"] if r["rule_id"] == "PAN-001")
    document_refs = [ref for ref in pan["evidence_refs"]
                     if ref.get("origin") in ("document", "derived")]
    assert document_refs
    for ref in document_refs:
        assert ref["document_filename"] == "sample_pan.pdf"   # from the audit row
        assert ref["page"] is not None and ref["confidence"] > 0
        assert ref["source"]
    adapter_refs = [ref for ref in pan["evidence_refs"]
                    if ref.get("origin") == "adapter"]
    assert adapter_refs and adapter_refs[0]["source"] == "MockPANAdapter"

    gst = next(r for r in profile["rule_results"] if r["rule_id"] == "GST-001")
    gst_adapters = [ref for ref in gst["evidence_refs"]
                    if ref.get("origin") == "adapter"]
    assert gst_adapters and gst_adapters[0]["source"] == "MockGSTAdapter"
    assert gst_adapters[0]["identifier"] == "07ABCDE1234F1Z5"

    # officer decision (if any) rides along
    client.post(f"/bidders/{bidder.id}/decisions",
                json={"decision": "SEND_FOR_CLARIFICATION",
                      "reason": "Udyam name mismatch"})
    decision = client.get(f"/bidders/{bidder.id}/profile").json()["decision"]
    assert decision["decision"] == "SEND_FOR_CLARIFICATION"
    assert decision["officer_name"] == "Priya Sharma"


def test_profile_404_before_evaluation(client, session):
    tender = seed_tender(session, tender_ref="GEM/2026/T/71005")
    bidder = Bidder(id=uuid4(), tender_id=tender.id, name="Unevaluated",
                    summary={})
    session.add(bidder)
    session.commit()

    missing = client.get(f"/bidders/{uuid4()}/profile")
    assert missing.status_code == 404
    not_run = client.get(f"/bidders/{bidder.id}/profile")
    assert not_run.status_code == 404
    assert "evaluate" in not_run.json()["detail"]


# --- 5. auth ------------------------------------------------------------------

def test_tender_upload_and_evaluate_require_jwt(client):
    pdf = (FIXTURES / "sample_tender.pdf").read_bytes()
    resp = TestClient(fastapi_app).post(
        "/tenders/upload",
        files={"file": ("sample_tender.pdf", pdf, "application/pdf")})
    assert resp.status_code == 401
    assert TestClient(fastapi_app).post(f"/bidders/{uuid4()}/evaluate").status_code == 401
    # reads stay open, like /dashboard and /bidders/{id}/audit
    assert client.get("/tenders").status_code == 200
