# SIH26100 — AI-Powered Bid Compliance Verification Platform for GeM Procurement

> **Smart India Hackathon 2026 · Team SIH26100**
> Problem Statement PS-1613 · Ministry of Commerce & Industry — GeM Procurement Wing

---

## What This System Does

Government procurement on GeM involves evaluating hundreds of bidders against complex tender requirements — manually. This platform automates that compliance verification using a **local AI model pipeline** that reads bidder documents, extracts structured evidence, and runs a deterministic rule engine to produce verdicts. A **Procurement Officer** reviews AI recommendations and makes the final decision.

```
Tender PDF  ──► Clause Extraction (LLM)  ──► Requirements
                                                   │
Bidder PDFs ──► Text/OCR/LLM Extraction ──► Evidence
                                                   │
                                          Deterministic Rule Engine
                                                   │
                              AI Verdict + Score + Risk + Recommendation
                                                   │
                                         Officer Reviews & Decides
                                                   │
                                           Immutable Audit Trail
```

**The AI never decides.** It outputs one of five verdicts per rule:
`SATISFIED` · `VIOLATION` · `NOT_VERIFIED` · `CONFLICT` · `NOT_APPLICABLE`

Only the Procurement Officer records the final decision (Approve / Reject / Send for Clarification).

---

## Local AI Model — Gemma & Ollama

### Why Local Models?

- **Data privacy**: Bidder documents contain sensitive PAN, GSTIN, financial data. Nothing leaves the server.
- **No API costs**: Government deployments cannot depend on paid third-party AI APIs.
- **Offline capability**: Can run in air-gapped government data centres.
- **Determinism**: Temperature 0, JSON-mode only — no hallucination of compliance verdicts.

### Model Used

| Role | Model | Server |
|------|-------|--------|
| Document field extraction | `gemma4` (default) or any Ollama-compatible model | Local Ollama |
| Tender clause extraction | Same model, different prompt schema | Local Ollama |

The model is configured via environment variables:

```
LLM_BASE_URL=http://localhost:11434    # Ollama server
LLM_MODEL=gemma4                       # or gemma2:2b, mistral, llama3.2, etc.
LLM_TIMEOUT=300                        # seconds before fallback
```

### How the LLM Is Constrained

The LLM is **only ever asked to extract fields**, never to judge compliance:

```python
# From backend/app/llm.py — system prompt excerpt
"You extract fields from Indian procurement documents.
 Return ONLY valid JSON with exactly these keys: {keys}.
 Use null for any value that is not fully and confidently present.
 Never infer, complete or guess a partially visible identifier."
```

Key constraints enforced in code:
- `format: "json"` — Ollama JSON mode, only valid JSON returned
- `temperature: 0` — fully deterministic, no creativity
- All extracted IDs validated against regex patterns (PAN/GSTIN/Udyam formats)
- Anything not legible → `null` → `NOT_VERIFIED` verdict (never a false positive)

### Extraction Pipeline

```
PDF upload
  │
  ├─► pdfplumber/PyMuPDF text layer (fast, native)
  │     If page has < 20 extractable characters:
  │
  └─► RapidOCR → page image at 200 DPI → OCR text
          │
          └─► LLM prompt with extracted text
                │
                └─► Strict JSON fields stored as ExtractedField rows
```

Document types supported: `PAN`, `GST`, `UDYAM`, `FINANCIAL`, `OEM_AUTHORIZATION`, `LOCAL_CONTENT`

---

## Rule Engine — Deterministic, Config-Driven

All 13 compliance rules live in `backend/app/config/rules_config.json`. **No business logic is hardcoded.**

### Rules Covered

| Rule ID | What It Checks |
|---------|---------------|
| `DEBARMENT-001` | Bidder not on GeM debarment list (critical — auto-rejects) |
| `ENTITY-CONSISTENCY-001` | Company name matches across PAN, GST, Udyam documents |
| `GST-REG-001` | Active GST registration |
| `PAN-VALID-001` | Valid PAN format |
| `UDYAM-REG-001` | Valid Udyam/MSME registration |
| `TURNOVER-001` | Annual turnover meets tender minimum |
| `MSME-CLASS-001` | MSME tier matches tender requirement |
| `LOCAL-CONTENT-001` | Local content percentage meets Make-in-India threshold |
| `OEM-AUTH-001` | OEM authorisation present (if bidder is reseller) |
| + 4 more | Financial, technical, and document-format rules |

### Verdict Logic (Kleene 3-Valued)

```
Evidence present  →  evaluate condition  →  SATISFIED or VIOLATION
Evidence absent   →  UNKNOWN             →  NOT_VERIFIED  (never VIOLATION)
Guard not met     →                      →  NOT_APPLICABLE
```

### Scoring

```
Score = Σ (rule_weight × 1 if SATISFIED) / Σ (rule_weight, excluding NOT_APPLICABLE)
Risk  = HIGH if score < 60% OR any critical rule fired
        MEDIUM if 60–84%
        LOW if >= 85%
```

### Changing Rules Without Code

Edit `backend/app/config/rules_config.json`, restart the backend. The rule engine reads it fresh at every evaluation — thresholds, weights, pass/fail verdicts, and applicability guards are all in JSON.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (Next.js)                    │
│  Dashboard · Tender List · Bidder Profile · Audit Trail  │
│  TypeScript + Tailwind + React                           │
└────────────────────────┬────────────────────────────────┘
                         │ REST API (JWT auth)
┌────────────────────────▼────────────────────────────────┐
│                   Backend (FastAPI)                      │
│                                                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
│  │  Document   │  │  Rule       │  │  Tender         │  │
│  │  Intel      │  │  Engine     │  │  Extraction     │  │
│  │  (Phase 3)  │  │  (Phase 5)  │  │  (Phase 7.5)    │  │
│  └──────┬──────┘  └──────┬──────┘  └────────┬────────┘  │
│         │                │                  │           │
│  ┌──────▼──────────────────────────────────▼────────┐  │
│  │             SQLAlchemy ORM · 11 Tables             │  │
│  │     PostgreSQL (prod) / SQLite (demo/Vercel)       │  │
│  └───────────────────────────────────────────────────┘  │
│                                                          │
│  ┌─────────────────────────┐                            │
│  │   Mock Gov. Adapters    │  GST · PAN · Udyam ·       │
│  │   (GovernmentSource     │  Debarment (mock only)     │
│  │    Adapter interface)   │                            │
│  └─────────────────────────┘                            │
└─────────────────────┬───────────────────────────────────┘
                      │ HTTP (local only)
┌─────────────────────▼───────────────────────────────────┐
│              Ollama (Local LLM Server)                   │
│              Model: gemma4 (or configured model)         │
│              JSON mode, temperature 0                    │
└─────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
sih26100-platform/
├── backend/                      FastAPI application
│   ├── app/
│   │   ├── main.py               All API routes (~50 endpoints)
│   │   ├── rule_engine.py        Deterministic rule evaluator
│   │   ├── extraction.py         PDF text + OCR + LLM pipeline
│   │   ├── tender_extraction.py  Tender clause extraction
│   │   ├── llm.py                Ollama client (JSON-only, temp 0)
│   │   ├── ocr.py                RapidOCR integration
│   │   ├── adapters.py           Mock government source adapters
│   │   ├── entity_resolution.py  Cross-document name normalisation
│   │   ├── audit.py              Immutable audit event writer
│   │   ├── auth.py               JWT + bcrypt officer auth
│   │   ├── database.py           Engine setup + schema init + seeding
│   │   ├── seed.py               Demo tender/bidder data seeder
│   │   ├── storage.py            File upload management
│   │   ├── config.py             Settings (pydantic-settings)
│   │   ├── config/
│   │   │   └── rules_config.json 13 rules, all thresholds, scoring weights
│   │   ├── db/
│   │   │   └── models.py         11 SQLAlchemy models
│   │   └── schemas/              Pydantic request/response schemas
│   ├── alembic/                  Database migrations
│   │   └── versions/0001_initial.py  Full schema (squashed migration)
│   ├── tests/                    109 backend tests (all passing)
│   │   ├── test_auth.py
│   │   ├── test_rule_engine.py
│   │   ├── test_adapters.py
│   │   ├── test_audit.py
│   │   ├── test_phase67.py       Mock adapter + scoring tests
│   │   ├── test_phase7.py        Audit trail + dashboard tests
│   │   └── test_phase75.py       Tender upload + extraction tests
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/                     Next.js 14 application
│   └── src/
│       ├── app/                  App Router pages
│       │   ├── login/            Officer login page
│       │   ├── dashboard/        Main overview with counts
│       │   ├── tenders/          Tender list + detail
│       │   └── bidders/          Bidder profile + audit
│       ├── components/
│       │   └── ui/               DemoNotice, shared UI components
│       └── lib/
│           └── config.ts         API base URL configuration
│
├── shared/                       TypeScript types (API contract)
├── vercel.json                   Vercel routing (frontend + backend)
├── docker-compose.yml            Full stack with PostgreSQL
└── .env.example                  Environment variable template
```

---

## Database Schema (11 Tables)

| Table | Purpose |
|-------|---------|
| `officers` | Procurement officer accounts + bcrypt passwords |
| `tenders` | Uploaded tenders with extracted clause data |
| `requirements` | Per-tender compliance requirements (from rules_config) |
| `bidders` | Bidder profiles with evaluation summary JSONB |
| `documents` | Uploaded bidder documents (PDF path + type) |
| `extracted_fields` | LLM-extracted field values with confidence + page |
| `verifications` | Government source adapter results (GST/PAN/Udyam status) |
| `rule_results` | Per-rule verdict for each bidder evaluation |
| `decisions` | Officer final decisions (Approve/Reject/Clarification) |
| `audit_events` | Immutable append-only event log (all actions) |

---

## API Endpoints (Key Routes)

```
POST /auth/login                    Officer login → JWT token
GET  /health                        Service health check

GET  /tenders                       List all tenders
POST /tenders/upload                Upload + extract tender PDF
GET  /tenders/{id}/requirements     Extracted compliance requirements

POST /tenders/{tid}/bidders         Register a bidder
POST /bidders/{id}/documents        Upload bidder document (PAN/GST/etc.)
POST /bidders/{id}/verify-identity  Cross-document entity resolution
POST /bidders/{id}/evaluate         Run rule engine → verdicts + score + risk
GET  /bidders/{id}/profile          Compliance profile + rule results
POST /bidders/{id}/decisions        Officer submits final decision

GET  /dashboard                     Summary counts for all tenders/bidders
GET  /bidders/{id}/audit            Complete audit trail for a bidder
```

---

## Getting Started

### Prerequisites

- Docker & Docker Compose
- [Ollama](https://ollama.com) installed locally (for LLM extraction)

### 1. Clone & Configure

```bash
git clone https://github.com/Manav5234/sih26100-platform.git
cd sih26100-platform
cp .env.example .env
# Edit .env — set JWT_SECRET to a random value (e.g. openssl rand -hex 32)
```

### 2. Pull the AI Model

```bash
ollama pull gemma4
# or: ollama pull gemma2:2b  (lighter, faster for demo)
```

Update `LLM_MODEL=gemma2:2b` in `.env` if you use a different model.

### 3. Start the Full Stack

```bash
docker compose up --build
```

- **Backend API**: http://localhost:8000
- **Frontend**: http://localhost:3000
- **Interactive API docs**: http://localhost:8000/docs

### 4. Run Backend Tests

```bash
cd backend && python -m pytest
# 109 tests, all green
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://postgres:postgres@postgres:5432/sih26100` | PostgreSQL connection string |
| `JWT_SECRET` | (required) | Secret for signing officer session tokens |
| `LLM_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `LLM_MODEL` | `gemma4` | Model name served by Ollama |
| `LLM_TIMEOUT` | `300` | Seconds to wait for LLM before template fallback |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | CORS allowed origins (comma-separated) |
| `UPLOAD_ROOT` | `/data/uploads` | Directory for uploaded PDF storage |

---

## Key Design Decisions for SIH Evaluators

### 1. AI Extracts, Rules Decide
The LLM is only a reader — it converts unstructured PDF text into structured JSON fields. A separate deterministic rule engine (no ML) computes verdicts. This separation means:
- Compliance logic is auditable and explainable
- Rules can be changed by editing JSON (no redeployment needed)
- No AI "hallucination" can produce a false compliance verdict

### 2. Kleene Three-Valued Logic
Missing evidence never becomes a `VIOLATION`. It becomes `NOT_VERIFIED`, which protects bidders from penalties when documents are illegible or missing — a critical fairness requirement in government procurement.

### 3. Immutable Audit Trail
Every action (tender upload, document extraction, rule evaluation, officer decision) is recorded as an append-only `AuditEvent`. The audit log cannot be modified or deleted through any API endpoint.

### 4. Mock Government Adapters
Real-time integration with GSTN, Udyam, PAN, and Debarment registries is behind a `GovernmentSourceAdapter` interface. The demo uses mock implementations that return realistic but simulated data. Swapping to a live adapter requires only implementing the interface — no rule engine changes needed.

### 5. No External AI APIs
All inference runs on a local Ollama server. The system works completely offline and handles sensitive procurement data without any data leaving the deployment environment.

---

## Live Demo (Vercel)

The platform is deployed at: **https://sih26100-platform.vercel.app**

> **Demo Notice**: The live deployment runs in serverless mode with SQLite (ephemeral /tmp). Government source checks use mock adapters — no real GSTN/Udyam/PAN API is called. LLM extraction is unavailable on Vercel (no Ollama); document uploads use template fallback values. For full functionality including local LLM extraction, run locally with Docker.

---

## Team

**SIH Team 26100** — Smart India Hackathon 2026
Problem Statement: PS-26100 — Automated Bid Compliance Verification for GeM
