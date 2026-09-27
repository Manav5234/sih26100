"""Phase 6: score, risk, recommendation — all read rules_config.json's
scoring block; no weights or bands reimplemented in code."""
import pytest
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, Bidder, Document, ExtractedField, Requirement, Tender
from app.rule_engine import (
    _critical_override_fired,
    calculate_risk,
    calculate_score,
    evaluate_bidder,
    generate_recommendation,
    load_config,
)

RULES = {r["rule_id"]: r for r in load_config()["rules"]}


def result(verdict, rule_id="GST-001"):
    return {"rule_id": rule_id, "verdict": verdict, "evidence_refs": [],
            "source": [], "legal_citation": None}


# --- calculate_score ---------------------------------------------------------

def test_score_excludes_not_applicable_from_both_sides():
    # SATISFIED 1.0 + NOT_VERIFIED 0.5 over 3 evaluated (NA dropped)
    out = calculate_score([result("SATISFIED"), result("NOT_APPLICABLE"),
                           result("NOT_VERIFIED"), result("CONFLICT")])
    assert out["score"] == 50            # 100 * 1.5 / 3
    assert out["evaluated"] == 3 and out["excluded"] == 1


def test_score_all_satisfied_is_100():
    assert calculate_score([result("SATISFIED")] * 4)["score"] == 100


def test_score_weights_come_from_config_not_code(monkeypatch):
    results = [result("SATISFIED"), result("NOT_VERIFIED")]
    assert calculate_score(results)["score"] == 75     # (1.0 + 0.5) / 2

    real_load = load_config()

    def patched():
        cfg = dict(real_load)
        cfg["scoring"] = dict(cfg["scoring"])
        cfg["scoring"]["weights"] = dict(cfg["scoring"]["weights"])
        cfg["scoring"]["weights"]["NOT_VERIFIED"] = 1.0   # config tweak
        return cfg

    monkeypatch.setattr("app.rule_engine.load_config", patched)
    assert calculate_score(results)["score"] == 100    # same code, new weights


def test_everything_not_applicable_guards_division_by_zero():
    out = calculate_score([result("NOT_APPLICABLE"), result("NOT_APPLICABLE")])
    assert out["score"] is None          # null, not 0, not 100
    assert out["manual_review"] is True  # flagged for a human
    assert out["evaluated"] == 0 and out["excluded"] == 2


# --- calculate_risk ----------------------------------------------------------

@pytest.mark.parametrize("score,critical,expected", [
    (95, False, "LOW"),
    (85, False, "LOW"),      # band boundary inclusive
    (84, False, "MEDIUM"),
    (60, False, "MEDIUM"),
    (59, False, "HIGH"),
    (50, False, "HIGH"),
    (70, True, "HIGH"),      # override fires below 85
    (95, True, "HIGH"),      # override wins over an excellent score
])
def test_risk_bands_from_config(score, critical, expected):
    assert calculate_risk(score, critical) == expected


def test_critical_override_beats_high_score():
    """The edge case most likely to break if someone 'simplifies' risk:
    score 95 + DEBARMENT-001 VIOLATION must be HIGH, not LOW."""
    results = [result("SATISFIED") for _ in range(19)] + \
        [result("VIOLATION", rule_id="DEBARMENT-001")]     # 19/20 -> score 95
    score = calculate_score(results)["score"]
    fired = _critical_override_fired(results,
                                     load_config()["critical_override_rule_ids"])
    assert score == 95 and fired is True
    assert calculate_risk(score, fired) == "HIGH"
    assert calculate_risk(score, False) == "LOW"    # same score, no override


def test_unscorable_score_maps_to_manual_review_risk():
    assert calculate_risk(None, False) == "MEDIUM"


# --- generate_recommendation -------------------------------------------------

def _full_profile_results():
    """Verdict mix shaped like Bidder C's e2e run."""
    conflict = {"rule_id": "ENTITY-CONSISTENCY-001", "verdict": "CONFLICT",
                "evidence_refs": [], "source": ["stored"], "legal_citation": None}
    gst = dict(result("SATISFIED"), rule_id="GST-001")
    pan = {"rule_id": "PAN-001", "verdict": "NOT_VERIFIED",
           "evidence_refs": [
               {"path": "pan.format_valid", "value": True, "origin": "derived"},
               {"path": "pan.status", "value": None, "origin": "unresolved",
                "missing": True}],
           "source": ["PAN:x"], "legal_citation": None}
    debar = {"rule_id": "DEBARMENT-001", "verdict": "NOT_VERIFIED",
             "evidence_refs": [{"path": "debarment.status", "value": None,
                                "origin": "unresolved", "missing": True}],
             "source": [], "legal_citation": None}
    return [gst, conflict, pan, debar]


def test_recommendation_builds_sentence_from_verdicts():
    text = generate_recommendation(_full_profile_results(), 62, "HIGH")
    assert "Bidder satisfies Tax requirements." in text
    assert "CONFLICT: Bidder identity must remain consistent across PAN, GST" \
        " and Udyam records (ENTITY-CONSISTENCY-001)." in text
    assert "NOT VERIFIED: Valid PAN (PAN-001) — unconfirmed source: pan.status." in text
    assert "NOT VERIFIED: Bidder not currently blacklisted/debarred" \
        " (DEBARMENT-001) — unconfirmed source: debarment.status." in text
    assert text.endswith("Recommendation: MANUAL REVIEW REQUIRED before qualification.")


def test_recommendation_low_risk_ending_and_no_llm():
    import inspect
    from app import rule_engine
    source = inspect.getsource(rule_engine.generate_recommendation)
    assert "llm" not in source and "extract_json" not in source   # template only
    text = generate_recommendation([result("SATISFIED")], 95, "LOW")
    assert text.startswith("Bidder satisfies Tax requirements.")
    assert text.endswith("Recommendation: no manual review indicated; "
                         "officer decision pending.")


# --- full profile object (wired into evaluate_bidder) -----------------------

@pytest.fixture
def sqlite_engine():
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return engine


def test_evaluate_bidder_returns_full_compliance_profile(sqlite_engine, monkeypatch):
    session = sessionmaker(bind=sqlite_engine)()
    tender = Tender(id=uuid4(), tender_ref="GEM/2026/T/PROFILE",
                    title="Profile test", minimum_turnover=None,
                    required_msme_tier=None, local_content_requirement_applicable=False,
                    bid_value_cr=None, required_local_content_class=None,
                    required_oem=None)
    bidder = Bidder(id=uuid4(), tender_id=tender.id, name="Profile Bidder",
                    legal_name="Profile Bidder", summary={})
    session.add_all([tender, bidder])
    session.flush()
    for index, rule in enumerate(load_config()["rules"], start=1):
        session.add(Requirement(id=uuid4(), tender_id=tender.id,
                                requirement_id=f"REQ-{index:03}",
                                title=rule["requirement"], category=rule["category"],
                                required_evidence=[], rule_id=rule["rule_id"],
                                status="PENDING"))
    gst_doc = Document(id=uuid4(), bidder_id=bidder.id, tender_id=tender.id,
                       doc_type="GST", file_path="/uploads/g.pdf",
                       extraction_method="text_layer")
    session.add(gst_doc)
    session.flush()
    # GSTIN is the registry key — gst.status now comes from MockGSTAdapter
    # (Phase 6.5), not the certificate's printed status line
    session.add(ExtractedField(id=uuid4(), document_id=gst_doc.id,
                               field_name="gstin", value="07ABCDE1234F1Z5",
                               confidence=1.0, page=1))
    session.commit()

    monkeypatch.setattr("app.rule_engine.engine", sqlite_engine)
    profile = evaluate_bidder(bidder.id, tender.id)

    assert set(profile) == {"bidder_id", "tender_id", "rule_results", "score",
                            "risk", "critical_override_fired", "recommendation",
                            "manual_review"}
    assert isinstance(profile["score"], int)
    assert profile["risk"] in ("LOW", "MEDIUM", "HIGH")
    assert isinstance(profile["recommendation"], str) and profile["recommendation"]
    assert profile["manual_review"] == (profile["risk"] in ("MEDIUM", "HIGH"))
    assert len(profile["rule_results"]) == 13
    # GST status evidence is the only extracted field -> exactly one SATISFIED
    satisfied = [r["rule_id"] for r in profile["rule_results"]
                 if r["verdict"] == "SATISFIED"]
    assert satisfied == ["GST-001"]
