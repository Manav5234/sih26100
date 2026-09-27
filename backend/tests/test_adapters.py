"""Phase 6.5: GovernmentSourceAdapter interface + mock wiring into
build_bidder_evidence. Adapters must never fabricate a pass for an
identifier they don't know, and must never be called without one."""
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.adapters import (GovernmentSourceAdapter, MockDebarmentAdapter,
                          MockGSTAdapter, MockPANAdapter, MockUdyamAdapter)
from app.db.models import Base, Bidder, Document, ExtractedField, Verification
from app.rule_engine import build_bidder_evidence

ALL_ADAPTERS = [MockPANAdapter, MockGSTAdapter, MockUdyamAdapter,
                MockDebarmentAdapter]
SEEDED = {                      # fixture identifiers -> registry status
    MockPANAdapter: ("ABCDE1234F", "VALID"),
    MockGSTAdapter: ("07ABCDE1234F1Z5", "ACTIVE"),
    MockUdyamAdapter: ("UDYAM-DL-05-0004567", "ACTIVE"),
    MockDebarmentAdapter: ("ABCDE1234F", "NOT_DEBARRED"),
}


@pytest.fixture
def session():
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def seed_bidder(session, docs: dict[str, dict]) -> Bidder:
    bidder = Bidder(id=uuid4(), tender_id=uuid4(), name="T",
                    legal_name="ABC Technologies Pvt Ltd", summary={})
    session.add(bidder)
    session.flush()
    for doc_type, fields in docs.items():
        doc = Document(id=uuid4(), bidder_id=bidder.id, tender_id=bidder.tender_id,
                       doc_type=doc_type, file_path=f"/uploads/{doc_type}.pdf",
                       extraction_method="text_layer")
        session.add(doc)
        session.flush()
        for name, value in fields.items():
            session.add(ExtractedField(id=uuid4(), document_id=doc.id,
                                       field_name=name, value=value,
                                       confidence=1.0, page=1))
    session.commit()
    return bidder


def test_interface_contract():
    for cls in ALL_ADAPTERS:
        assert issubclass(cls, GovernmentSourceAdapter)
        identifier, _ = SEEDED[cls]
        response = cls().verify(identifier)
        assert set(response) == {"status", "matched_fields", "source", "confidence"}
        assert response["source"] == cls.__name__
        assert isinstance(response["confidence"], (int, float))


@pytest.mark.parametrize("cls", ALL_ADAPTERS)
def test_seeded_identifiers_get_registry_status(cls):
    identifier, expected = SEEDED[cls]
    assert cls().verify(identifier)["status"] == expected
    assert cls().verify(f"  {identifier.lower()}  ")["status"] == expected  # normalizes


@pytest.mark.parametrize("cls", ALL_ADAPTERS)
def test_unknown_identifier_is_never_a_fabricated_pass(cls):
    response = cls().verify("UDYAM-XX-99-9999999")
    assert response["status"] == "NOT_VERIFIED"      # not ACTIVE / VALID / NOT_DEBARRED
    assert response["confidence"] == 0.0
    assert response["matched_fields"] == {}


def test_adapter_statuses_populate_evidence_and_are_audited(session):
    bidder = seed_bidder(session, {
        "PAN": {"pan": "ABCDE1234F", "name": "ABC TECHNOLOGIES PVT LTD"},
        "GST": {"gstin": "07ABCDE1234F1Z5", "legal_name": "ABC TECHNOLOGIES PVT LTD"},
        "UDYAM": {"udyam_number": "UDYAM-DL-05-0004567",
                  "enterprise_name": "ABC TECHNOLOGIES PVT LTD"},
    })
    ev = build_bidder_evidence(session, bidder)

    assert ev["pan"]["status"] == "VALID"
    assert ev["gst"]["status"] == "ACTIVE"
    assert ev["udyam"]["status"] == "ACTIVE"
    assert ev["debarment"]["status"] == "NOT_DEBARRED"   # keyed by PAN number
    for path in ("pan.status", "gst.status", "udyam.status", "debarment.status"):
        assert ev["_refs"][path]["origin"] == "adapter"
        assert ev["_refs"][path]["source"].startswith("Mock")

    rows = session.query(Verification).filter_by(bidder_id=bidder.id).all()
    assert {r.source for r in rows} == {"MockPANAdapter", "MockGSTAdapter",
                                        "MockUdyamAdapter", "MockDebarmentAdapter"}
    assert all(r.status == "MATCHED" for r in rows)
    assert all(set(r.response) == {"status", "matched_fields", "source",
                                   "confidence"} for r in rows)


def test_gst_status_comes_from_adapter_not_the_printed_certificate_line(session):
    # certificate prints "Status of Registration: Active" AND carries a GSTIN:
    # the registry adapter's ACTIVE wins; the printed line is never evidence
    bidder = seed_bidder(session, {
        "GST": {"gstin": "07ABCDE1234F1Z5", "status": "Active"},
    })
    ev = build_bidder_evidence(session, bidder)
    assert ev["gst"]["status"] == "ACTIVE"
    assert ev["_refs"]["gst.status"]["origin"] == "adapter"


def test_no_identifier_means_adapter_never_called(session):
    # Bidder B scenario: Udyam document missing entirely
    bidder = seed_bidder(session, {"PAN": {"pan": "ABCDE1234F"}})
    ev = build_bidder_evidence(session, bidder)
    assert "udyam" not in ev                       # no block, no status, no ref
    assert "gst" not in ev
    assert "debarment" in ev and ev["debarment"]["status"] == "NOT_DEBARRED"
    assert "udyam.status" not in ev["_refs"]       # zero fabrication, zero failure theatre
    assert session.query(Verification).count() == 2   # only PAN + debarment calls


def test_unextracted_number_means_adapter_never_called(session):
    # Bidder A's scanned Udyam: number redacted in Phase 3 -> value None
    bidder = seed_bidder(session, {
        "UDYAM": {"udyam_number": None, "enterprise_name": "ABC TECHNOLOGIES PVT LTD"},
    })
    ev = build_bidder_evidence(session, bidder)
    assert "status" not in ev.get("udyam", {})
    assert session.query(Verification).count() == 0


def test_unknown_identifier_records_attempt_but_leaves_status_null(session):
    bidder = seed_bidder(session, {"PAN": {"pan": "ZZZZZ9999Z"}})
    ev = build_bidder_evidence(session, bidder)
    assert "status" not in ev.get("pan", {})       # NOT_VERIFIED -> null -> rule NV
    assert ev["_refs"]["pan.status"]["adapter_status"] == "NOT_VERIFIED"
    # PAN + debarment both attempted with the unknown PAN
    rows = session.query(Verification).all()
    assert {r.source for r in rows} == {"MockPANAdapter", "MockDebarmentAdapter"}
    assert all(r.status == "NOT_FOUND" for r in rows)
