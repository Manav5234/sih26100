"""Government source adapters (original spec section 12).

HARD PROJECT RULE: mock implementations only. This codebase never calls
live GSTN/Udyam/PAN/efiling services. Each adapter answers from a seeded
registry keyed by the identifier Phase 3 extracted; an identifier the
registry does not know comes back NOT_VERIFIED — never a fabricated pass.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class GovernmentSourceAdapter(ABC):
    """Interface: verify(identifier) -> {status, matched_fields, source,
    confidence}. Statuses are registry vocabulary ('ACTIVE', 'VALID',
    'NOT_DEBARRED') because rules_config.json conditions compare against
    those exact strings."""

    source: str

    @abstractmethod
    def verify(self, identifier: str) -> dict:
        raise NotImplementedError


class _SeededMock(GovernmentSourceAdapter):
    """Registry lookup shared by all mocks: identifier -> seeded entry."""

    _registry: dict[str, dict] = {}

    def verify(self, identifier: str) -> dict:
        key = (identifier or "").strip().upper()
        entry = self._registry.get(key)
        if entry is None:
            return {"status": "NOT_VERIFIED", "matched_fields": {},
                    "source": self.source, "confidence": 0.0}
        return {"status": entry["status"],
                "matched_fields": {"identifier": key,
                                   "legal_name": entry["legal_name"]},
                "source": self.source, "confidence": 1.0}


class MockPANAdapter(_SeededMock):
    """Income Tax PAN registry (simulated)."""

    source = "MockPANAdapter"
    _registry = {
        "ABCDE1234F": {"status": "VALID",
                       "legal_name": "ABC TECHNOLOGIES PVT LTD"},
    }


class MockGSTAdapter(_SeededMock):
    """GSTN registration registry (simulated) — replaces trusting the
    'Status: Active' line printed on the uploaded certificate."""

    source = "MockGSTAdapter"
    _registry = {
        "07ABCDE1234F1Z5": {"status": "ACTIVE",
                            "legal_name": "ABC TECHNOLOGIES PVT LTD"},
    }


class MockUdyamAdapter(_SeededMock):
    """Udyam/MSME registry (simulated). Only complete identifiers extracted
    from bidder documents are ever sent here."""

    source = "MockUdyamAdapter"
    _registry = {
        "UDYAM-DL-05-0004567": {"status": "ACTIVE",
                                "legal_name": "ABC TECHNOLOGIES PVT LTD"},
    }


class MockDebarmentAdapter(_SeededMock):
    """Debarment/blacklist check (simulated), keyed by PAN. None of the
    seeded bidders is a debarred case; debarred entities are a future
    bidder scenario."""

    source = "MockDebarmentAdapter"
    _registry = {
        "ABCDE1234F": {"status": "NOT_DEBARRED",
                       "legal_name": "ABC TECHNOLOGIES PVT LTD"},
    }
