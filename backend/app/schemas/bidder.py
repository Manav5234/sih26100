from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class BidderCreate(BaseModel):
    tender_id: UUID
    name: str
    legal_name: str | None = None


class BidderOut(BaseModel):
    id: UUID
    tender_id: UUID
    name: str
    legal_name: str | None = None
