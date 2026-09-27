from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ExtractedFieldOut(BaseModel):
    """One evidence object: value + document + page + confidence + method."""
    field_name: str
    value: str | None = None
    confidence: float
    page: int | None = None
    extraction_method: str | None = None


class DocumentOut(BaseModel):
    id: UUID | None = None
    doc_type: str
    status: str  # present | missing | unreadable | pending
    file_path: str | None = None
    uploaded_at: datetime | None = None
    extraction_method: str | None = None
    fields: list[ExtractedFieldOut] = []


class DocumentListResponse(BaseModel):
    bidder_id: UUID
    documents: list[DocumentOut]
