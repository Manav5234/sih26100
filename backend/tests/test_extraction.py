"""Phase 3 document pipeline tests.

OCR is real (PP-OCR models ship with the wheel); the LLM is stubbed so tests
never depend on a running Ollama server.
"""
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import extraction
from app.db.models import Base, Bidder, Document, ExtractedField, Tender
from app.extraction import extract_document, read_pages
from app.main import _document_out

FIXTURES = Path(__file__).parent / "fixtures"
PAN_PDF = FIXTURES / "sample_pan.pdf"
UDYAM_PDF = FIXTURES / "sample_udyam_scanned.pdf"


class LLMStub:
    def __init__(self, monkeypatch):
        self.response: dict = {}
        self.prompts: list[str] = []

        def fake(prompt: str, *, keys: list[str], timeout: float = 0) -> dict:
            self.prompts.append(prompt)
            return dict(self.response)

        monkeypatch.setattr(extraction.llm, "extract_json", fake)


def test_text_layer_extraction_uses_default_confidence(monkeypatch):
    stub = LLMStub(monkeypatch)
    stub.response = {"pan": "ABCDE1234F", "name": "ABC TECHNOLOGIES PVT LTD"}

    result = extract_document(str(PAN_PDF), "PAN")

    assert result.method == "text_layer"
    by_name = {f.field_name: f for f in result.fields}
    assert by_name["pan"].value == "ABCDE1234F"
    assert by_name["pan"].page == 1
    assert by_name["pan"].confidence == 0.7        # text-layer default
    assert by_name["pan"].extraction_method == "text_layer"


def test_image_only_page_falls_back_to_ocr(monkeypatch):
    stub = LLMStub(monkeypatch)
    stub.response = {"udyam_number": None, "enterprise_name": "ABC TECHNOLOGIES PVT LTD",
                     "category": "Micro"}

    pages = read_pages(str(UDYAM_PDF))
    assert pages[0].method == "ocr"                # no extractable text layer
    assert pages[0].ocr_confidence is not None and pages[0].ocr_confidence > 0

    result = extract_document(str(UDYAM_PDF), "UDYAM")

    assert result.method == "ocr"
    by_name = {f.field_name: f for f in result.fields}
    assert by_name["enterprise_name"].value == "ABC TECHNOLOGIES PVT LTD"
    assert by_name["enterprise_name"].confidence == 0.5   # OCR default
    assert by_name["udyam_number"].value is None          # null, never guessed
    assert stub.prompts and "UDYAM-DL-05-0004567" in stub.prompts[0]  # OCR reached the LLM


def test_truncated_key_identifier_becomes_null(monkeypatch):
    """A partial identifier (truncated OCR result, damaged scan) is rejected
    by the deterministic format check: the LLM cannot know text is missing,
    so the check nulls it instead of storing it as evidence."""
    stub = LLMStub(monkeypatch)
    stub.response = {"udyam_number": "UDYAM-DL-05-0003",     # partial result
                     "enterprise_name": "ABC TECHNOLOGIES PVT LTD",
                     "category": "Micro"}

    result = extract_document(str(UDYAM_PDF), "UDYAM")
    by_name = {f.field_name: f for f in result.fields}

    assert by_name["udyam_number"].value is None            # never a partial ID
    assert by_name["enterprise_name"].value == "ABC TECHNOLOGIES PVT LTD"


def test_unreadable_key_field_marks_document_unreadable():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    tender = Tender(id=uuid4(), tender_ref="GEM/2026/T/00456", title="ABC Equipment Procurement")
    bidder = Bidder(id=uuid4(), tender_id=tender.id, name="ABC Technologies Pvt Ltd")
    doc = Document(id=uuid4(), bidder_id=bidder.id, tender_id=tender.id,
                   doc_type="UDYAM", file_path="/uploads/x.pdf", extraction_method="ocr")
    session.add_all([tender, bidder, doc])
    session.flush()
    session.add(ExtractedField(id=uuid4(), document_id=doc.id, field_name="udyam_number",
                               value=None, confidence=0.0, page=None))
    session.add(ExtractedField(id=uuid4(), document_id=doc.id, field_name="enterprise_name",
                               value="ABC TECHNOLOGIES PVT LTD", confidence=0.5, page=1))
    session.commit()

    out = _document_out(doc)
    assert out.status == "unreadable"             # key identifier is null
    assert {f.field_name: f.value for f in out.fields}["udyam_number"] is None

    # Same document with a readable key identifier is 'present'.
    doc.extracted_fields[0].value = "UDYAM-DL-05-00038217"
    session.commit()
    assert _document_out(doc).status == "present"

    # No upload at all is 'missing' at the list level, 'pending' before extraction.
    pending = Document(id=uuid4(), bidder_id=bidder.id, tender_id=tender.id,
                       doc_type="GST", file_path="/uploads/y.pdf", extraction_method=None)
    session.add(pending)
    session.commit()
    assert _document_out(pending).status == "pending"
