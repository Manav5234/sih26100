"""Phase 7: persistence + audit trail + officer dashboard endpoints.

Covers: rule_results / summary.profile storage (replace-on-re-evaluate),
per-stage audit events, GET /dashboard reading the stored record,
GET /bidders/{id}/audit ordering, officer decision recording, and the
seeding idempotency that keeps a re-run from duplicating audit rows.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
from app.rule_engine import evaluate_bidder, load_config

RULES = load_config()["rules"]


@pytest.fixture
def engine():
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine):
    return sessionmaker(bind=engine)()


def seed(session, tender_ref="GEM/2026/T/70001", bidder_name="Bidder A"):
    tender = Tender(id=uuid4(), tender_ref=tender_ref, title="Phase 7 test",
                    minimum_turnover=5.0, required_msme_tier=None,
                    local_content_requirement_applicable=False,
                    bid_value_cr=None, required_local_content_class=None,
                    required_oem=None)
    bidder = Bidder(id=uuid4(), tender_id=tender.id, name=bidder_name,
                    legal_name="ABC Technologies Pvt Ltd", summary={})
    session.add_all([tender, bidder])
    session.flush()
    for index, rule in enumerate(RULES, start=1):
        session.add(Requirement(id=uuid4(), tender_id=tender.id,
                                requirement_id=f"REQ-{index:03}",
                                title=rule["requirement"], category=rule["category"],
                                required_evidence=[], rule_id=rule["rule_id"],
                                status="PENDING"))
    session.commit()
    return tender, bidder


def add_doc(session, bidder, doc_type, fields):
    doc = Document(id=uuid4(), bidder_id=bidder.id, tender_id=bidder.tender_id,
                   doc_type=doc_type, file_path=f"/uploads/{doc_type}.pdf",
                   extraction_method="text_layer")
    session.add(doc)
    session.flush()
    for name, value in fields.items():
        session.add(ExtractedField(id=uuid4(), document_id=doc.id,
                                   field_name=name, value=value,
                                   confidence=0.9, page=1))
    session.commit()
    return doc


def stages(session, bidder_id=None, tender_id=None):
    query = session.query(AuditEvent)
    if bidder_id is not None:
        query = query.filter(AuditEvent.bidder_id == bidder_id)
    if tender_id is not None:
        query = query.filter(AuditEvent.tender_id == tender_id)
    return [(r.event_type, r.payload) for r in
            query.order_by(AuditEvent.created_at).all()]


# --- 2. persisted submission record -----------------------------------------

def test_evaluate_bidder_persists_profile_and_rule_results(engine, session, monkeypatch):
    tender, bidder = seed(session)
    add_doc(session, bidder, "GST",
            {"gstin": "07ABCDE1234F1Z5", "legal_name": "ABC TECHNOLOGIES PVT LTD"})
    monkeypatch.setattr("app.rule_engine.engine", engine)

    profile = evaluate_bidder(bidder.id, tender.id)

    rows = session.query(RuleResult).filter_by(bidder_id=bidder.id).all()
    assert len(rows) == len(RULES)                      # one row per requirement
    assert {r.verdict for r in rows} == {r["verdict"] for r in profile["rule_results"]}
    assert all(r.evidence is not None for r in rows)

    session.refresh(bidder)
    stored = bidder.summary["profile"]
    assert stored["score"] == profile["score"]
    assert stored["risk"] == profile["risk"]
    assert stored["manual_review"] == profile["manual_review"]
    assert stored["recommendation"] == profile["recommendation"]
    assert bidder.summary["evaluated_at"]
    # hard rule 5: each stored result carries rule id + legal source + evidence
    for result in stored["rule_results"]:
        assert result["rule_id"] and result["legal_citation"] is not None
        assert isinstance(result["evidence_refs"], list)

    evaluate_bidder(bidder.id, tender.id)               # re-evaluation replaces
    assert session.query(RuleResult).filter_by(bidder_id=bidder.id).count() == len(RULES)


def test_evaluation_writes_rules_evaluated_and_conflict_audit(engine, session, monkeypatch):
    tender, bidder = seed(session, bidder_name="Bidder C")
    add_doc(session, bidder, "GST",
            {"gstin": "07ABCDE1234F1Z5", "legal_name": "ABC TECHNOLOGIES PVT LTD"})
    # Phase 4 stored a name conflict -> ENTITY-CONSISTENCY-001 -> CONFLICT
    summary = dict(bidder.summary)
    summary["entity_consistency"] = {"verdict": "CONFLICT", "page_refs": [],
                                     "outliers": ["UDYAM"], "missing": []}
    bidder.summary = summary
    session.commit()
    monkeypatch.setattr("app.rule_engine.engine", engine)

    profile = evaluate_bidder(bidder.id, tender.id)
    assert profile["critical_override_fired"] is True

    events = stages(session, bidder_id=bidder.id)
    assert [e[0] for e in events].count("RULES_EVALUATED") == 1
    rule_event = next(d for name, d in events if name == "RULES_EVALUATED")
    assert rule_event["score"] == profile["score"] and rule_event["risk"] == "HIGH"

    conflict = next(d for name, d in events if name == "CONFLICT_DETECTED")
    assert "ENTITY-CONSISTENCY-001" in conflict["rule_ids"]


def test_source_checked_audit_event_per_adapter_call(engine, session):
    tender, bidder = seed(session)
    add_doc(session, bidder, "PAN", {"pan": "ABCDE1234F",
                                     "name": "ABC TECHNOLOGIES PVT LTD"})
    from app.rule_engine import build_bidder_evidence
    ev = build_bidder_evidence(session, bidder)
    assert ev["pan"]["status"] == "VALID"

    checked = [d for name, d in stages(session, bidder_id=bidder.id)
               if name == "SOURCE_CHECKED"]
    # PAN registry + debarment registry, one event each
    assert {d["source"] for d in checked} == {"MockPANAdapter",
                                              "MockDebarmentAdapter"}
    assert all(d["identifier"] == "ABCDE1234F" for d in checked)


# --- 3. GET /dashboard -------------------------------------------------------

def test_dashboard_reads_stored_profile_and_decisions(engine, session, monkeypatch):
    tender, bidder = seed(session, bidder_name="Bidder A")
    tender2 = Tender(id=uuid4(), tender_ref="GEM/2026/T/70002", title="Other")
    undecided = Bidder(id=uuid4(), tender_id=tender2.id, name="Bidder B",
                       legal_name="ABC Technologies Pvt Ltd", summary={})
    session.add_all([tender2, undecided])
    session.commit()
    bidder.summary = {"profile": {"score": 90, "risk": "LOW", "manual_review": False,
                                  "recommendation": "clean"},
                      "evaluated_at": "2026-09-27T10:00:00+00:00"}
    session.commit()

    monkeypatch.setattr("app.main.engine", engine)
    with TestClient(fastapi_app) as client:
        body = client.get("/dashboard").json()

    assert body["count"] == 2 and len(body["bidders"]) == 2
    first = body["bidders"][0]
    assert first["tender_ref"] == "GEM/2026/T/70001"
    assert first["score"] == 90 and first["risk"] == "LOW"
    assert first["status"] == "AWAITING_DECISION"
    assert first["pending_review"] is False and first["recommendation"] == "clean"

    unevaluated = body["bidders"][1]
    assert unevaluated["status"] == "AWAITING_EVALUATION"
    assert unevaluated["score"] is None and unevaluated["pending_review"] is True


# --- 4. GET /bidders/{id}/audit ---------------------------------------------

def test_bidder_audit_timeline_is_ordered_and_starts_at_tender_upload(engine, session,
                                                                      monkeypatch):
    tender, bidder = seed(session, bidder_name="Bidder C")
    base = datetime.now(timezone.utc)
    sequence = [
        ("TENDER_UPLOADED", None, {"tender_ref": tender.tender_ref}),
        ("REQUIREMENTS_EXTRACTED", None, {"requirements": len(RULES)}),
        ("BIDDER_CREATED", bidder.id, {"name": bidder.name}),
        ("DOCUMENT_UPLOADED", bidder.id, {"doc_type": "PAN"}),
        ("OCR_COMPLETED", bidder.id, {"doc_type": "UDYAM"}),
        ("FIELDS_EXTRACTED", bidder.id, {"doc_type": "UDYAM"}),
        ("SOURCE_CHECKED", bidder.id, {"source": "MockGSTAdapter"}),
        ("RULES_EVALUATED", bidder.id, {"score": 65}),
        ("CONFLICT_DETECTED", bidder.id, {"rule_ids": ["ENTITY-CONSISTENCY-001"]}),
    ]
    for offset, (stage_name, event_bidder, detail) in enumerate(sequence):
        session.add(AuditEvent(id=uuid4(), event_type=stage_name,
                               tender_id=tender.id, bidder_id=event_bidder,
                               payload=detail,
                               created_at=base + timedelta(microseconds=offset)))
    session.commit()

    monkeypatch.setattr("app.main.engine", engine)
    with TestClient(fastapi_app) as client:
        body = client.get(f"/bidders/{bidder.id}/audit").json()
        missing = client.get(f"/bidders/{uuid4()}/audit")

    assert missing.status_code == 404
    assert body["bidder_id"] == str(bidder.id)
    assert [e["stage"] for e in body["events"]] == [s for s, _, _ in sequence]
    # spec shape on every event
    for event in body["events"]:
        assert set(event) == {"bidder_id", "tender_id", "stage", "detail", "timestamp"}
    assert body["events"][0]["bidder_id"] is None      # tender-level stage
    assert body["events"][3]["bidder_id"] == str(bidder.id)


# --- 6/1: officer decision -> audit event -----------------------------------

def test_officer_decision_is_recorded_with_officer_reason_and_audit(engine, session,
                                                                    monkeypatch):
    tender, bidder = seed(session, bidder_name="Bidder A")
    officer = Officer(id=uuid4(), name="Priya Sharma",
                      email="priya@example.gov.in",
                      password_hash="x", role=OfficerRole.INSPECTOR)
    session.add(officer)
    session.commit()

    from app.auth import create_access_token
    token = create_access_token(officer.id, officer.role.value)
    monkeypatch.setattr("app.main.engine", engine)
    monkeypatch.setattr("app.database.engine", engine)   # get_db() in auth

    with TestClient(fastapi_app) as client:
        resp = client.post(f"/bidders/{bidder.id}/decisions",
                           json={"decision": "SEND_FOR_CLARIFICATION",
                                 "reason": "Udyam certificate illegible"},
                           headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["officer_name"] == "Priya Sharma"
    assert body["decision"] == "SEND_FOR_CLARIFICATION"

    decision = session.query(Decision).filter_by(bidder_id=bidder.id).one()
    assert decision.reason == "Udyam certificate illegible"
    assert decision.officer_name == "Priya Sharma" and decision.created_at

    event = next(d for name, d in stages(session, bidder_id=bidder.id)
                 if name == "OFFICER_DECISION_RECORDED")
    assert event["decision"] == "SEND_FOR_CLARIFICATION"

    monkeypatch.setattr("app.main.engine", engine)
    with TestClient(fastapi_app) as client:
        row = client.get("/dashboard").json()["bidders"][0]
    assert row["status"] == "SEND_FOR_CLARIFICATION" and row["pending_review"] is False

    bad = TestClient(fastapi_app).post(
        f"/bidders/{bidder.id}/decisions",
        json={"decision": "MAYBE", "reason": "nope"},
        headers={"Authorization": f"Bearer {token}"})
    assert bad.status_code == 400


# --- 1/8: idempotent re-seeding ---------------------------------------------

def test_pending_stages_skips_everything_already_done():
    from scripts.phase5_evaluate import pending_stages

    wanted = ["sample_pan.pdf", "sample_gst.pdf"]
    fresh = pending_stages(docs=set(), identity=None, profile=None, wanted=wanted)
    assert fresh == {"documents": wanted, "identity": True, "evaluate": True}

    done = pending_stages(docs={"PAN", "GST"},
                          identity={"verdict": "MATCH"},
                          profile={"score": 90}, wanted=wanted)
    assert done == {"documents": [], "identity": False, "evaluate": False}

    partial = pending_stages(docs={"PAN"}, identity=None, profile=None,
                             wanted=wanted)
    assert partial["documents"] == ["sample_gst.pdf"]
