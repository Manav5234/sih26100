# SIH26100 — AI-Powered Bid Compliance Verification Platform for GeM Procurement

A tender-aware decision-support workspace for procurement officers:

```
Tender PDF → Requirements → Bidder Documents → Evidence → Verification
          → Risk → Officer Decision → Audit
```

**AI verifies. Evidence explains. Officer decides.** The system never
qualifies or disqualifies a bidder — it outputs one of five verdicts
(`SATISFIED`, `VIOLATION`, `NOT_VERIFIED`, `CONFLICT`, `NOT_APPLICABLE`)
plus a recommendation, and only a Procurement Officer records a final
decision (Approve / Reject / Send for Clarification).

## Stack

| Layer     | Tech |
|-----------|------|
| Backend   | FastAPI, SQLAlchemy, Alembic, PostgreSQL (JSONB) |
| PDF text  | pdfplumber / PyMuPDF; PaddleOCR for scanned pages |
| LLM       | Local Ollama (schema-strict JSON extraction for tender clauses) |
| Frontend  | Next.js + TypeScript + Tailwind |
| Rules     | `backend/app/config/rules_config.json` — read at runtime, never hardcoded |

## Demo environment notice

Government-source checks run through a `GovernmentSourceAdapter` interface
with **mock implementations** (`MockGSTAdapter`, `MockUdyamAdapter`,
`MockPANAdapter`, `MockDebarmentAdapter`). No live GSTN/Udyam/PAN API is
called. The same interface accepts an authorized live adapter later — only
the implementation behind it changes.

## Getting started

```bash
git clone https://github.com/Manav5234/sih26100-platform.git
cd sih26100-platform
docker compose up --build
```

- Backend: http://localhost:8000 (health: `GET /health` → `{"status":"ok","service":"sih26100-backend"}`)
- Frontend: http://localhost:3000

Migrations run automatically on backend boot (`alembic upgrade head`).

### Backend tests

```bash
cd backend && python -m pytest
```

## Repository layout

```
backend/     FastAPI app (app/), Alembic migrations, tests
frontend/    Next.js app (src/app, src/components)
shared/      TypeScript types shared with the API contract
tests/       Cross-cutting fixtures
```

## Configuration

Copy `.env.example` → `.env`. Key variables:

- `DATABASE_URL` — PostgreSQL connection string
- `JWT_SECRET` — PO session signing secret (required)
- `LLM_BASE_URL` / `LLM_MODEL` — extraction model (defaults to local Ollama)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
