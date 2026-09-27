from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str


class AuthLoginRequest(BaseModel):
    email: str
    password: str


class AuthOfficer(BaseModel):
    id: UUID
    role: str


class AuthLoginResponse(BaseModel):
    token: str
    officer: AuthOfficer
