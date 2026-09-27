"""Phase 4: ENTITY-CONSISTENCY-001 cross-document identity resolution.

Three seeded-bidder cases from the plan:
  Bidder A — PAN/GST/Udyam all match            -> MATCH
  Bidder B — Udyam document missing entirely     -> NOT_VERIFIED (not CONFLICT)
  Bidder C — Udyam name is the outlier           -> CONFLICT showing the outlier
"""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import AuditEvent, Base, Bidder, Document, ExtractedField, Tender
from app.entity_resolution import (
    NAME_FIELDS,
    RULE_ID,
    build_identity_evidence,
    compare_entities,
    normalize_entity_name,
)
from app.main import app as fastapi_app


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def seed_bidder(session, names_by_type: dict[str, str], tender_ref: str = "GEM/2026/T/00456"):
    """Create tender + bidder + one document per {doc_type: entity name}."""
    tender = Tender(id=uuid4(), tender_ref=tender_ref, title="ABC Equipment Procurement")
    bidder = Bidder(id=uuid4(), tender_id=tender.id, name="ABC Technologies Pvt Ltd",
                    legal_name="ABC Technologies Pvt Ltd", summary={})
    session.add_all([tender, bidder])
    session.flush()
    for doc_type, name in names_by_type.items():
        doc = Document(id=uuid4(), bidder_id=bidder.id, tender_id=tender.id,
                       doc_type=doc_type, file_path=f"/uploads/{doc_type}.pdf",
                       extraction_method="text_layer")
        session.add(doc)
        session.flush()
        session.add(ExtractedField(id=uuid4(), document_id=doc.id,
                                   field_name=NAME_FIELDS[doc_type],
                                   value=name, confidence=1.0, page=1))
    session.commit()
    return bidder


# --- Step 1: normalization (rule order: case-fold, collapse, strip, suffix) ---

@pytest.mark.parametrize("raw,expected", [
    # 1. case-fold
    ("ABC TECHNOLOGIES PVT LTD", "abc technologies pvt ltd"),
    ("  abc technologies pvt ltd  ", "abc technologies pvt ltd"),
    # 2. collapse whitespace (incl. tabs / multi-space)
    ("ABC  Technologies \t Pvt Ltd", "abc technologies pvt ltd"),
    # 3. strip punctuation (periods, commas as word separators: "P.Ltd" must not become "pltd")
    ("ABC Technologies Pvt. Ltd.", "abc technologies pvt ltd"),
    ("ABC Technologies P. Ltd", "abc technologies pvt ltd"),
    ("ABC Technologies, Pvt Ltd", "abc technologies pvt ltd"),
    # 4. legal suffixes -> canonical
    ("ABC Technologies Private Limited", "abc technologies pvt ltd"),
    ("ABC Technologies Pvt Limited", "abc technologies pvt ltd"),
    ("ABC Technologies Private Ltd", "abc technologies pvt ltd"),
    ("ABC Technologies Limited", "abc technologies ltd"),
    ("ABC Technologies LLP", "abc technologies llp"),
    ("ABC & Co", "abc co"),
    ("ABC and Co", "abc co"),
    ("ABC & Company", "abc co"),
    ("ABC Company", "abc co"),
    # combined
    ("Abc   Technologies PVT.  Limited", "abc technologies pvt ltd"),
    # missing stays missing
    (None, None),
    ("   ", None),
])
def test_normalize_entity_name(raw, expected):
    assert normalize_entity_name(raw) == expected


def test_suffix_normalization_applies_only_at_end():
    # "Pvt Ltd" inside a company name must not be touched mid-string.
    assert normalize_entity_name("Pvt Ltd Trading Company") == "pvt ltd trading co"


# --- Bidder A: all three names match -> MATCH -------------------------------

def test_bidder_a_all_names_match(db):
    # Deliberately three different raw spellings of the same entity.
    bidder = seed_bidder(db, {
        "PAN": "ABC TECHNOLOGIES PVT LTD",
        "GST": "ABC Technologies Private Limited",
        "UDYAM": "Abc Technologies P. Ltd.",
    }, tender_ref="GEM/2026/T/10001")

    evidence = build_identity_evidence(db, bidder.id)

    assert evidence["rule_id"] == RULE_ID
    assert evidence["verdict"] == "MATCH"
    assert evidence["source_documents"] == ["PAN", "GST", "UDYAM"]
    assert evidence["missing"] == []
    assert evidence["outliers"] == []
    assert all(p["verdict"] == "MATCH" for p in evidence["pairs"])
    assert evidence["normalized_values"] == {
        "PAN": "abc technologies pvt ltd",
        "GST": "abc technologies pvt ltd",
        "UDYAM": "abc technologies pvt ltd",
    }
    assert evidence["page_refs"] == [
        {"source": "PAN", "field": "name", "document_id": str(doc_id(db, bidder.id, "PAN")),
         "page": 1, "confidence": 1.0},
        {"source": "GST", "field": "legal_name", "document_id": str(doc_id(db, bidder.id, "GST")),
         "page": 1, "confidence": 1.0},
        {"source": "UDYAM", "field": "enterprise_name",
         "document_id": str(doc_id(db, bidder.id, "UDYAM")), "page": 1, "confidence": 1.0},
    ]


def doc_id(db, bidder_id, doc_type):
    return db.query(Document).filter_by(bidder_id=bidder_id, doc_type=doc_type).first().id


# --- Bidder B: Udyam missing entirely -> NOT_VERIFIED -----------------------

def test_bidder_b_udyam_missing_is_not_verified(db):
    bidder = seed_bidder(db, {
        "PAN": "ABC TECHNOLOGIES PVT LTD",
        "GST": "ABC Technologies Pvt Ltd",
        # no UDYAM document at all
    }, tender_ref="GEM/2026/T/10002")

    evidence = build_identity_evidence(db, bidder.id)

    assert evidence["verdict"] == "NOT_VERIFIED"        # not CONFLICT, not MATCH
    assert evidence["source_documents"] == ["PAN", "GST"]
    assert evidence["missing"] == ["UDYAM"]
    assert {tuple(p["sources"]): p["verdict"] for p in evidence["pairs"]} == {
        ("PAN", "GST"): "MATCH",            # the pairing we can check agrees
        ("PAN", "UDYAM"): "NOT_VERIFIED",   # nothing to compare against
        ("GST", "UDYAM"): "NOT_VERIFIED",
    }
    assert evidence["normalized_values"]["UDYAM"] is None


# --- Bidder C: Udyam is the outlier -> CONFLICT with the specific strings ----

def test_bidder_c_conflict_shows_udyam_as_outlier(db):
    bidder = seed_bidder(db, {
        "PAN": "ABC Technologies Pvt Ltd",
        "GST": "ABC Technologies Pvt Ltd",
        "UDYAM": "ABC Tech Solutions",
    }, tender_ref="GEM/2026/T/10003")

    evidence = build_identity_evidence(db, bidder.id)

    assert evidence["verdict"] == "CONFLICT"
    assert evidence["outliers"] == ["UDYAM"]           # not just "3 names, mismatch"
    assert evidence["missing"] == []

    by_pair = {tuple(p["sources"]): p for p in evidence["pairs"]}
    assert by_pair[("PAN", "GST")]["verdict"] == "MATCH"
    assert by_pair[("PAN", "UDYAM")] == {
        "sources": ["PAN", "UDYAM"],
        "verdict": "CONFLICT",
        "values": {"PAN": "abc technologies pvt ltd", "UDYAM": "abc tech solutions"},
    }
    assert by_pair[("GST", "UDYAM")]["values"] == {
        "GST": "abc technologies pvt ltd", "UDYAM": "abc tech solutions",
    }


# --- Evidence stored on the bidder's compliance profile ---------------------

def test_evidence_stored_on_bidder_profile(db, monkeypatch):
    bidder = seed_bidder(db, {
        "PAN": "ABC Technologies Pvt Ltd",
        "GST": "ABC Technologies Pvt Ltd",
        "UDYAM": "ABC Tech Solutions",
    }, tender_ref="GEM/2026/T/10004")

    monkeypatch.setattr("app.main.engine", db.get_bind())
    client = TestClient(fastapi_app)
    resp = client.post(f"/bidders/{bidder.id}/verify-identity")

    assert resp.status_code == 200
    body = resp.json()
    assert body["rule_id"] == RULE_ID
    assert body["verdict"] == "CONFLICT"
    assert body["outliers"] == ["UDYAM"]

    db.expire_all()
    stored = db.get(Bidder, bidder.id).summary["entity_consistency"]
    assert stored == body                                   # same evidence shape stored
    assert set(stored) >= {"rule_id", "verdict", "source_documents",
                           "normalized_values", "page_refs"}
    assert db.query(AuditEvent).filter_by(event_type="ENTITY_CONSISTENCY_CHECK").count() == 1


# --- Sanity: compare_entities entry point -----------------------------------

def test_compare_entities_direct():
    result = compare_entities("ABC Technologies Pvt Ltd", "ABC Technologies Pvt Ltd",
                              "ABC Tech Solutions")
    assert result["verdict"] == "CONFLICT"
    assert result["outliers"] == ["UDYAM"]

    result = compare_entities("ABC Technologies Pvt Ltd", "ABC Technologies Pvt Ltd", None)
    assert result["verdict"] == "NOT_VERIFIED"
    assert result["missing"] == ["UDYAM"]
