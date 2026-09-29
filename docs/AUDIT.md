# SIH26100 — Verification Audit

Audited against `docs/PROBLEM_STATEMENT.md` (official text, Section 7).
Run date: 2026-09-29. Commit audited: `bdfd640` (main).
Method: every claim below was executed. Nothing is marked DONE that was not run.

Environment note: this machine is Windows. Backend tests ran on **Python 3.14.5**
with already-installed (not pinned) deps; CI runs 3.11 + `requirements.txt`.
`backend/.env` exists locally and points at `localhost:5432` / Ollama `:11434`.

---

## 1. BUILD CHECK

| # | Command | Result |
|---|---|---|
| 1 | `cd backend && python -m pytest -q` | **PASS** — `129 passed, 25 warnings in 54.49s` |
| 2 | `cd backend && ruff check .` | **FAIL** — `Found 387 errors` (exit 1) |
| 3 | `cd backend && ruff check app scripts --statistics` | **FAIL** — 11 errors (5 F541, 2 F401, 2 B905, 1 S105, 1 S110) |
| 4 | `cd frontend && npm run lint` | **PASS** — 0 errors, 8 warnings (`react-hooks/set-state-in-effect`) |
| 5 | `cd frontend && npm run build` | **PASS** — Next 16.3.4, TypeScript OK, 15 routes |
| 6 | `docker compose up --build -d` | **FAIL (exit 1)** — `ports are not available: ...0.0.0.0:3000 bind: Only one usage` |
| 7 | `curl http://localhost:8000/health` (after 6) | **PASS** — `{"status":"ok","service":"sih26100-backend"}` |
| 8 | `docker build --target runner -t audit-frontend ./frontend` | **PASS** |
| 9 | `docker run -p 3005:3000 audit-frontend` + `GET /login` | **PASS** — HTTP 200, 17743 bytes |

Notes, bluntly:

- **Port 3000 on this machine is held by an unrelated `node` process (pid 20368,
  invisible to PowerShell → WSL).** That is an environment problem, not a repo
  bug — but it means `docker compose up` did **not** fully boot during this audit.
  I verified the frontend image boots by running it on :3005 instead.
- `docker-compose.override.yml:19` builds only the `deps` stage and runs
  `npm run dev`, and `docker-compose.override.yml:24` mounts
  `./frontend/next.config.js` — **that file does not exist** (the repo has
  `next.config.mjs`). Under `docker compose watch` that mount silently creates a
  directory instead of a file. The default `docker compose up` therefore does not
  start the production image at all.
- **CI (`.github/workflows/ci.yml`) does not run `ruff`.** Backend CI is
  `pip install` + `pytest` only, so the 387 ruff errors are invisible to CI.
- `pip install -r requirements.txt` was **not** re-run (would downgrade the
  host interpreter's packages mid-session); test run above used installed deps.
- Pytest warnings worth reading: `jwt.InsecureKeyLengthWarning: The HMAC key is
  11 bytes long` — the JWT secret in use is below the RFC 7518 minimum (see §7).

### Boot verification (what actually came up)

```
postgres:16-alpine   Up (healthy)
backend              Up, /health 200
frontend (on :3005)  Up, /login 200
```

---

## 2. CODE MAP

### Backend routes (14 total, from `/openapi.json` of a live instance)

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/health` | none | `main.py:184` |
| POST | `/auth/login` | none | `main.py:193`, rate-limited 5/15min |
| POST | `/tenders/upload` | **officer** | `main.py:255`, LLM extract + fallback |
| GET | `/tenders` | **none** | `main.py:324` |
| GET | `/tenders/{id}/requirements` | **none** | `main.py:334` |
| POST | `/bidders` | **none** | `main.py:398` (creates a bidder!) |
| POST | `/bidders/{id}/documents` | **none** | `main.py:414` (runs OCR+LLM!) |
| GET | `/bidders/{id}/documents` | **none** | `main.py:486` |
| POST | `/bidders/{id}/verify-identity` | **none** | `main.py:510` (mutates) |
| GET | `/dashboard` | **none** | `main.py:538` |
| GET | `/bidders/{id}/audit` | **none** | `main.py:581` |
| POST | `/bidders/{id}/decisions` | **officer** | `main.py:604` |
| POST | `/bidders/{id}/evaluate` | **officer** | `main.py:686` |
| GET | `/bidders/{id}/profile` | **none** | `main.py:703` |

**3 of 14 routes require authentication.**

### DB tables (11, `app/db/models.py`)

`officers`, `tenders`, `requirements`, `bidders`, `documents`,
`extracted_fields`, `verifications`, `rule_results`, `decisions`,
`audit_events` + `Base`. Migrations: `alembic/versions/0001_initial.py`.

### Frontend pages (`frontend/src/app`)

| Route | File | What it does |
|---|---|---|
| `/` | `page.tsx` (69 L) | Landing |
| `/login` | `login/page.tsx` (240 L) | Officer login → cookie |
| `/dashboard` | `dashboard/page.tsx` (284 L) | All bidders, score/risk/status |
| `/tenders` | `tenders/page.tsx` (379 L) | List + **tender PDF upload** |
| `/tenders/[id]` | `tenders/[id]/page.tsx` | Requirements list (read-only) |
| `/bidders` | `bidders/page.tsx` (410 L) | List + **create bidder** |
| `/bidders/[id]` | `bidders/[id]/page.tsx` (1168 L) | Upload docs, verify identity, evaluate, evidence drawer, record decision |
| `/audit` | `audit/page.tsx` (348 L) | Per-bidder timeline |
| `/settings` | `settings/page.tsx` (208 L) | Static info, adapter list |
| `/~offline` | `~offline/page.tsx` | PWA offline page |
| `/api/auth/{login,logout,token}` | `app/api/auth/*` | Cookie set/clear/read |
| middleware | `src/middleware.ts` | Redirects to `/login` if no cookie |

No `/bids`, no bidder-facing route, no auditor route.

### Background jobs

**None.** Extraction, OCR and LLM calls run synchronously inside the upload
request (`main.py:460`). A slow Ollama (timeout `LLM_TIMEOUT=300`s) holds the
HTTP request open for up to 5 minutes.

### Scripts (`backend/scripts/`)

`create_officer.py` (only way to make a login), `dev_up.ps1`, `live_check.py`,
`live_check_llm.py`, `make_sample_docs.py`, `phase1_paddleocr_test.py`,
`phase3_demo.py`, `phase5_evaluate.py` (demo seeder, **not** an eval harness).

---

## 3. MOCK / FAKE SCAN

| Location | What | Compliance path? |
|---|---|---|
| `backend/app/adapters.py:43-51` | `MockPANAdapter` seeded registry (`ABCDE1234F` → `VALID`) | **YES** — feeds `pan.status` → `PAN-001` verdict |
| `backend/app/adapters.py:53-62` | `MockGSTAdapter` (`07ABCDE1234F1Z5` → `ACTIVE`) | **YES** — feeds `gst.status` → `GST-001` |
| `backend/app/adapters.py:64-72` | `MockUdyamAdapter` (`UDYAM-DL-05-0004567` → `ACTIVE`) | **YES** — feeds `UDYAM-001` |
| `backend/app/adapters.py:75-84` | `MockDebarmentAdapter` (any seeded PAN → `NOT_DEBARRED`) | **YES** — `DEBARMENT-001` returns **SATISFIED** from a fabricated registry |
| `backend/app/tender_extraction.py:43-50` | `TEMPLATE_TENDER_FIELDS` — `minimum_turnover: 5.0`, `bid_value_cr: 80.0`, `local_content class_2` hardcoded | **YES** — used whenever the LLM fails; these are tender thresholds the rule engine evaluates against |
| `backend/app/main.py:217` | `DEMO_NOTICE` string | Display only (honest) |
| `frontend/src/components/ui/DemoNotice.tsx:13-15` | "results simulated via mock adapter… No live GSTN/Udyam/PAN" | Display only (honest) |
| `frontend/src/app/settings/page.tsx:169-196` | Adapter list with mock statuses | Display only (honest) |
| `backend/app/auth.py:21` | `_DUMMY_BCRYPT_HASH` | Timing-safe login, not a verdict |
| `backend/tests/fixtures/sample_*.pdf` (7 files) | Fixtures | Tests only |
| `backend/scripts/make_sample_docs.py:132` | `np.random.default_rng(42)` for scan noise | Generator only, not runtime |
| `frontend/src/app/serwist/[path]/route.ts:4` | `randomUUID()` | Service-worker cache revision, not compliance |
| `backend/app/config/rules_config.json` `scoring.weights.NOT_VERIFIED = 0.5` | **Half credit for unverified evidence** | **YES** — see §5, score 50 with zero verified evidence |

**Not found anywhere:** `Math.random`, `random()` on a verdict path, canned LLM
responses, `lorem`, hardcoded pass/fail in application code, `TODO`/`FIXME`.
The rule engine is genuinely deterministic (`rule_engine.py`, 978 lines).

Two categories of fake remain, and both matter:

1. **Every government registry check is a seeded dictionary** (§3 rows 1-4).
   Honest in the UI, but `DEBARMENT-001 → SATISFIED` and `GST-001 → SATISFIED`
   in a demo are produced by mock data, not verification.
2. **Tender thresholds are fabricated on LLM failure** (row 5) and then flow
   into `TURNOVER-001` / `LOCAL-CONTENT-001`. The response *is* labelled
   `extraction_method: "template_fallback"`, but the officer UI shows
   "Minimum turnover: 5.0" as if it came from the uploaded PDF. This directly
   violates project rule §8.7 of the PS doc ("Never invent tender requirements").

---

## 4. AI REALITY CHECK — one document, end to end

Two full runs were executed: one where the LLM was unreachable (the default
Docker configuration) and one where it was reachable.

### Run A — Docker (default `docker compose up`)

Startup log (`docker logs sih26100-platform-backend-1`):

```
startup llm endpoint=http://localhost:11434 unreachable (ConnectError: [Errno 111] Connection refused)
  — extraction will fall back to template_fallback
```

Inside the container `LLM_BASE_URL` is unset, so it comes from the baked
`backend/.env` → `localhost:11434` **inside the container** → always refused.
**A stock `docker compose up` has no working LLM, ever.**

Uploaded `sample_pan.pdf`, `sample_gst.pdf`, `sample_udyam_scanned.pdf`:

```
PAN   [200] method=text_layer status=unreadable  pan=null  name=null
GST   [200] method=text_layer status=unreadable  gstin=null legal_name=null status=null
UDYAM [200] method=ocr        status=unreadable  udyam_number=null enterprise_name=null
```

`POST /evaluate` on that bidder:

```
score=50 risk=HIGH manual_review=True critical=False
13 rules: 10x NOT_VERIFIED, 3x NOT_APPLICABLE, 0x SATISFIED, 0x VIOLATION
```

**Verdict: honest.** No fake pass. OCR genuinely ran on the image-only Udyam
(`extraction_method: "ocr"`).

Tender upload in the same run:

```
extraction_method=template_fallback  turnover=5.0  bid=80.0  lc=True/class_2  reqs=13
```

The numbers 5.0 / 80.0 / class_2 are **not from the PDF** — they are
`tender_extraction.py:43`. `reqs=13` is one-per-config-rule, i.e. the engine
evaluates a requirement set that was never read from the document.

### Run B — host `uvicorn` on `127.0.0.1:8001` + local Ollama (`gemma4`)

Startup log: `startup llm endpoint=http://localhost:11434 reachable model=gemma4 loaded`.

Tender: `extraction_method=llm turnover=5.0 bid=80.0 lc=True/class_2_local_supplier reqs=8`
— the LLM read the real PDF (8 clauses it could map to rules, vs the
template's blanket 13).

Documents (real values, real pages, real confidences):

```
PAN   method=text_layer status=present :: pan=ABCDE1234F@p1/c1.0; name=ABC TECHNOLOGIES PVT LTD@p1/c1.0
GST   method=text_layer status=present :: gstin=07ABCDE1234F1Z5@p1/c1.0; legal_name=ABC TECHNOLOGIES PVT LTD@p1/c1.0; status=Active@p1/c1.0
UDYAM method=ocr        status=present :: udyam_number=UDYAM-DL-05-0004567@p1/c1.0; enterprise_name=...@p1/c1.0; category=Micro@p1/c0.9
FIN   method=text_layer status=present :: turnover_cr=12.4@p1/c0.7; financial_year=2024-25@p1/c0.7
```

`POST /evaluate` → `score=81 risk=MEDIUM manual_review=True`:
`PAN-001 SATISFIED, GST-001 SATISFIED, UDYAM-001 SATISFIED, TURNOVER-001 SATISFIED,
DEBARMENT-001 SATISFIED (mock), ENTITY-CONSISTENCY NOT_VERIFIED (until
verify-identity), OEM-AUTH-001 NOT_VERIFIED, LOCAL-CONTENT-001 NOT_VERIFIED`.

### Answers

| Question | Answer |
|---|---|
| Is the LLM actually called? | **Yes**, when reachable — `app/llm.py:50` POSTs to `{LLM_BASE_URL}/api/chat`. Not called at all in the default Docker setup. |
| Provider / model? | **Local Ollama**, `LLM_MODEL=gemma4` (`config.py:37-40`). No cloud provider, no API key. |
| OCR actually called? | **Yes** — `rapidocr-onnxruntime` via `app/ocr.py`; confirmed on the image-only Udyam fixture. |
| Output schema-validated? | **PARTIAL.** `format:"json"` + `temperature:0` (`llm.py:41-44`), then key filtering (`extraction.py` `_clean`, `_number`), then `KEY_FORMATS` regex gates on PAN/GSTIN/Udyam (`extraction.py:46-52`). There is **no** jsonschema/pydantic validation of the model's object; a wrong-typed value becomes `null` rather than an error. |
| Is pass/fail decided by deterministic code? | **Yes.** `rule_engine.evaluate_rule` is Kleene three-valued logic over `rules_config.json`; the LLM is never asked for a verdict (verified in `llm.py` — it only receives extraction prompts). |
| Does failure become UNVERIFIED/NEEDS_REVIEW, never a fake pass? | **For bidder documents: yes** — LLM down ⇒ all fields `null` ⇒ `NOT_VERIFIED`. **For tenders: no** — failure silently swaps in fabricated thresholds (`tender_extraction.py:80`). The only "fake pass" risk is `MockDebarmentAdapter` returning `NOT_DEBARRED` for a seeded PAN. |
| Registry call failure? | **Unreachable state does not exist.** There is no live registry at all, so there is no `UNVERIFIED`/`FORMAT_ONLY` per-source status — only `MATCHED`/`NOT_FOUND` from a dictionary (`rule_engine.py:660-665`). |
| Test coverage of failure? | `test_phase75.py:218-244` simulates `httpx.ConnectError` for tender upload (asserts `template_fallback`). **No test simulates LLM failure for a bidder document, and no test simulates a registry/adapter failure.** |

---

## 5. REQUIREMENTS MATRIX

Legend: **DONE** = ran it end to end · **PARTIAL** = ran it, incomplete ·
**STUB** = interface/scaffold with fake or non-functional internals ·
**MISSING** = absent.

### Expected Solution (official items 1-14)

| # | Official requirement | Status | Evidence / how verified |
|---|---|---|---|
| 1 | Integrate with relevant Government portals/databases for automated verification | **STUB** | `app/adapters.py` — ABC interface + 4 seeded mocks; docstring line 3 says "HARD PROJECT RULE: mock implementations only". No credentials, no HTTP client, no live endpoint anywhere in `app/`. |
| 2 | Verify Udyam/MSME status and other statutory registrations | **PARTIAL** | Ran: Udyam doc → `UDYAM-001 SATISFIED`. It verifies a *document* + a *mock registry*, not the Udyam portal. No NSIC/Startup/MCA registrations exist. |
| 3 | Verify GST registration **and return filing status** | **PARTIAL** | Ran: `GST-001 SATISFIED` from certificate + `MockGSTAdapter`. **Return-filing status is not implemented anywhere** (no rule, no field, no adapter). `GST-002` (threshold) is literally `condition: "N/A — informational only"`. |
| 4 | Verify PAN and Income Tax compliance | **PARTIAL** | Ran: `PAN-001 SATISFIED` via `KEY_FORMATS` regex + `MockPANAdapter`. Format check + dictionary, no Income Tax portal. |
| 5 | Check Make in India / local content requirements | **PARTIAL** | Ran: `LOCAL-CONTENT-001` present, `NOT_VERIFIED` without a `LOCAL_CONTENT` doc; `classify()` + tender class from config. Works when a local-content PDF is uploaded. |
| 6 | Verify EPFO/ESIC compliance wherever applicable | **STUB** | `LABOUR-EPFO-001` condition is `bidder.employee_count >= 20 THEN epfo.status == 'REGISTERED'` — but **no document schema or bidder field can ever produce `employee_count` or `epfo.status`** (`extraction.py:28-35`). Permanently `NOT_VERIFIED`; the NA guard can never fire either. |
| 7 | Verify Startup India, NSIC and OEM authorization requirements | **PARTIAL** | OEM: `OEM-AUTH-001` + `OEM_AUTHORIZATION` schema, real extraction verified in tests (`test_phase67.py:41`). **Startup India: 0 references. NSIC: 0 references** (grepped `app/`). |
| 8 | Perform DigiLocker / document verification | **MISSING** | No DigiLocker integration, no token/OAuth flow, no document-authenticity check. "Document verification" today = local text/OCR extraction + regex format gates. |
| 9 | Identify blacklisting and debarment status | **STUB** | `MockDebarmentAdapter` (`adapters.py:75`) returns `NOT_DEBARRED` for exactly one seeded PAN, `"ABC TECHNOLOGIES PVT LTD"`. Any other PAN ⇒ `NOT_VERIFIED`. |
| 10 | Other applicable statutory and tender-specific compliance requirements | **PARTIAL** | 13 rules in `rules_config.json`, clause→rule mapping validated against the config (`tender_extraction.py:233`), thresholds re-read from the tender (`tender_override_allowed`). **Gap: only rules the tender LLM chooses to map get evaluated** — Run B produced 8 requirements from a config that has 13; unmapped rules are silently never checked. |
| 11 | Use AI to identify missing, inconsistent or non-compliant information | **PARTIAL** | Missing: yes (missing doc ⇒ `NOT_VERIFIED`, `GET /documents` reports `missing`). Inconsistent: **entity name only** — `entity_resolution.py:29` `SOURCES = (PAN, GST, UDYAM)` names. No PAN/GSTIN/address/date/figure contradiction detection. |
| 12 | Generate an overall Compliance Score and Risk Level | **PARTIAL** | Ran both runs: `score=50/HIGH` (LLM down) and `score=81/MEDIUM` (LLM up), `risk_bands` from config, `critical_override` respected. **Flaw: `NOT_VERIFIED` weights 0.5** (`rules_config.json`), so a bidder with *zero* verified evidence scores 50/100. |
| 13 | Provide an AI-generated recommendation to the Procurement Officer | **DONE** | Ran: `generate_recommendation` (`rule_engine.py:848`) returns a per-rule sentence list + "MANUAL REVIEW REQUIRED before qualification". Deterministic template over verdicts — correct by design ("AI recommends, officer decides"). |
| 14 | Maintain an auditable record of verification and compliance checks | **PARTIAL** | Ran: `GET /bidders/{id}/audit` returned a chronological timeline (TENDER_UPLOADED → DOCUMENT_UPLOADED → FIELDS_EXTRACTED → SOURCE_CHECKED → RULES_EVALUATED → OFFICER_DECISION_RECORDED). **No hash chain, no verify endpoint, no export.** `audit.py` just inserts rows. |

### Key Capabilities (official items 1-6)

| # | Capability | Status | Evidence |
|---|---|---|---|
| 1 | Multi-Portal Integration — Udyam, GSTN, PAN, GeM etc. | **STUB** | 4 seeded mock adapters, no network calls (`adapters.py:3-7`). GeM is not integrated either — tenders are uploaded as PDFs. |
| 2 | AI Document Verification — automated extraction, validation & cross-verification | **PARTIAL** | Extraction: real and verified (Run B, pages + confidences, OCR fallback). Validation: `KEY_FORMATS` regex. Cross-verification: names only. No bbox/OCR-region evidence, no authenticity check. |
| 3 | Automated Compliance Engine — tender-specific eligibility & statutory checks | **DONE** | `rule_engine.py` — config-driven, three-valued, tender overrides; 16 unit tests in `test_rule_engine.py` + 10 in `test_scoring.py`; ran end to end twice. |
| 4 | Risk & Compliance Scoring — score with bidder risk classification | **PARTIAL** | Runs and is config-driven, but `NOT_VERIFIED = 0.5` credit inflates scores of unevidenced bidders (§5 #12). |
| 5 | AI Recommendation Engine — identifies gaps, discrepancies, recommends status | **PARTIAL** | Gaps: yes (lists every `NOT_VERIFIED` with its missing evidence path). Discrepancies: only entity-name conflicts. Recommendation exists and is shown. |
| 6 | Audit Trail & Dashboard — centralized verification status, evidence & decision support | **PARTIAL** | `GET /dashboard` + `GET /bidders/{id}/audit` + evidence drawer all ran. No tamper evidence, no PDF report, no clarification workflow. |

### Expected Impact (official bullets)

**None can be marked DONE — they are outcome claims, not features, and nothing
in the repo measures them.**

| Claim | Status | Note |
|---|---|---|
| 60–80% reduction in verification effort | **MISSING** | No measurement, no baseline, no `/eval`. |
| Faster tender evaluation & award | **MISSING** | Untested; in default Docker config extraction returns a fabricated tender in ms because the LLM never runs. |
| Improved compliance & transparency | **PARTIAL** | Evidence drawer + audit timeline exist; per-source honesty (`VERIFIED/FORMAT_ONLY/UNVERIFIED`) does not. |
| Reduced human errors & inconsistencies | **PARTIAL** | Deterministic rules, but `NOT_VERIFIED = 0.5` and mock registries introduce their own errors. |
| Better bidder screening & risk identification | **PARTIAL** | Risk bands run; contradiction detection is names-only. |
| Standardized verification across CPSEs | **PARTIAL** | `rules_config.json` v1.1.0 with `last_verified` is the right idea. |
| Complete auditability & traceability | **PARTIAL** | Append-only rows, no hash chain, no verification endpoint, no export. |

---

## 6. PORTAL CHECK

### Login
**Yes, for officers only.** `POST /auth/login` (bcrypt, timing-safe dummy hash,
rate limit 5/15min), JWT HS256 8h, accepted from `Authorization` header or
httpOnly cookie (`auth.py:42-61`). Frontend sets the cookie through
`/api/auth/login` (`httpOnly, sameSite=lax`, `secure` only when
`ENVIRONMENT=production`).

**No bidder login. No auditor login. No user management** — the only account
creation path is `scripts/create_officer.py`, and no officer exists on a fresh
database, so a first-time `docker compose up` gives you a login page nobody can
log into unless they find that script (it is not mentioned in `README.md`).

### Roles enforced server-side?
**No.** `require_role()` exists (`auth.py:68-73`) and is **never used by any
route** — it is only referenced by `tests/test_auth.py:192-211`. Every
authenticated route accepts any role. Roles are `ADMIN | INSPECTOR | VIEWER`
(`db/models.py`) — there is no `OFFICER`, `BIDDER` or `AUDITOR` role.

Measured auth matrix against a live instance (no credentials sent):

```
GET    /health                              -> 200
GET    /tenders                             -> 200
GET    /dashboard                           -> 200
GET    /tenders/{id}/requirements           -> 200
GET    /bidders/{id}/documents              -> 200
GET    /bidders/{id}/profile                -> 200
GET    /bidders/{id}/audit                  -> 200
POST   /bidders                             -> 200
POST   /bidders/{id}/verify-identity        -> 200
POST   /bidders/{id}/documents              -> 200   (real PDF upload + OCR + LLM, no session)
POST   /bidders/{id}/evaluate               -> 401
POST   /bidders/{id}/decisions              -> 401
POST   /tenders/upload                      -> 401
```

**11 of 14 routes need no session; only `/tenders/upload`, `/evaluate` and
`/decisions` are protected.**

Frontend middleware (`src/middleware.ts`) only checks that the cookie **exists**
— it never validates it, and the API does not enforce the session on reads.
The UI is effectively security through obscurity of UUIDs.

### Bidder portal
**Absent.** No bidder registration, no "my bids", no bidder-facing tender list,
no bidder document upload (an officer uploads on the bidder's behalf:
`bidders/[id]/page.tsx:199`), no draft/submit with hash receipt, no status
timeline for the bidder, no clarification inbox.

### Officer portal
**Present and largely working** (all confirmed to exist; the pages render 200):

- Create tender: `/tenders` → `POST /tenders/upload` (PDF) ✅
- Confirm extracted requirements: **read-only** — `/tenders/[id]` lists
  requirements, there is no approve/edit step ❌
- Bids dashboard: `/dashboard` with score, risk, status, recommendation ✅
- Bid detail with evidence: `/bidders/[id]` — doc upload, `verify-identity`,
  `evaluate`, verdict table, evidence drawer with page/value/confidence ✅
- Decide: `recordDecision` with **client-enforced** mandatory reason
  (`bidders/[id]/page.tsx:213-216`); the API accepts `reason: ""` (verified:
  `empty-reason decision -> 200`) ⚠️
- Clarifications: `SEND_FOR_CLARIFICATION` exists only as a decision enum value —
  no request, no deadline, no bidder-facing inbox ❌

---

## 7. SECURITY CHECK

| Area | Finding | Severity |
|---|---|---|
| Secrets in git | **Clean.** `git log --all -- "**/.env"` → no commits; only `.env.example` tracked. | OK |
| Secrets in artifacts | **`backend/.env` is baked into the Docker image** — no `backend/.dockerignore`, `Dockerfile:22` does `COPY . .`. Verified: `docker run --rm --entrypoint sh … ls -la /app/.env` → 1238 bytes, contains `JWT_SECRET=test-secret`. | High |
| JWT secret in use | Live container reports `JWT_SECRET=test-secret` — compose interpolated it from the **ambient Windows environment**, overriding the compose default. PyJWT warns it is 11 bytes (< 32 required). Anyone with the source knows the signing key. | High |
| Roles | Not enforced (see §6). | High |
| IDOR | **Worse than IDOR: no auth on reads at all.** Any client can `GET /bidders/{any-uuid}/profile`, `/audit`, `/documents` and `POST /bidders`, `POST /bidders/{id}/verify-identity`. UUID guessing is irrelevant when unauthenticated access works. | Critical |
| Authenticated-but-unbounded work | `POST /bidders/{id}/documents` (unauthenticated) triggers PDF read + render + **OCR + LLM call** up to `LLM_TIMEOUT=300`s. That is an unauthenticated resource-exhaustion vector. | High |
| File upload validation | `content_type != "application/pdf"` check only (`main.py:270,429`) — a spoofable header. **No magic-byte check.** Extension is taken from the user filename (`storage.py:62`), so `file=@x.php` + `Content-Type: application/pdf` is stored as `{uuid}.php`. Mitigated: no static mount serves `/uploads`, files are read only via `pymupdf`, 10MB cap, name replaced by UUID. | Medium |
| Path traversal | `storage.get_path` prefixes `/uploads/` and joins — `..` segments are not explicitly rejected (`storage.py:69-74`), but the only caller passes a path the server itself generated. | Low |
| CORS | **Correct.** `allow_origins` defaults to `http://localhost:3000`; probed with `Origin: http://evil.example` → no `Access-Control-Allow-Origin` returned; with `http://localhost:3000` → echoed. Credentials enabled. | OK |
| Rate limits | Login only, **in-memory, per-process** (`main.py:164-177`) — resets on restart and does not survive >1 worker. No limit on uploads or evaluation. | Medium |
| HTTPS / Secure cookie | `secure` flag only when `ENVIRONMENT=production` (`api/auth/login/route.ts:10`); defaults to false. | Low (dev) |
| Audit tamper resistance | Plain inserts, no hash chain, no `verify` endpoint, no immutability enforcement at DB level. | Medium |
| Sensitive data exposure | Extracted PAN/GSTIN values are returned in API responses and shown in the UI in clear text; no redaction. | Medium |
| Decision integrity | API accepts `reason: ""` — the "every override needs a written reason" rule is enforced only in the browser. | Medium |

---

## 8. TOP 10 GAPS (ranked by demo impact)

1. **No bidder portal at all (G1).** The PS is about *bidders participating in
   GeM procurement*; today an officer fabricates bidders and uploads documents
   for them. No bidder login, no bidder submission, no status, no clarifications.
2. **11 of 14 API routes are unauthenticated (G1).** Including document upload
   and the whole compliance profile of every bidder. A judge who opens DevTools
   sees the data with no session. Fix before anything else.
3. **In the default Docker setup the LLM never runs (G2).** `docker compose up`
   → every tender is `template_fallback` and every document is `unreadable`.
   The demo works only if you know to run a host Ollama *and* start the backend
   outside the container (or set `LLM_BASE_URL=http://host.docker.internal:11434`).
4. **Template fallback fabricates tender thresholds (G2).** `minimum_turnover=5.0`,
   `bid_value_cr=80.0` appear in the UI as if extracted. This is the exact
   failure mode the PS's own project rules forbid (§8.7). It should fail loudly
   with `NEEDS_REVIEW`, not invent a tender.
5. **All government verification is seeded mock data (G7).** `DEBARMENT-001`
   and `GST-001` "pass" off a two-entry dictionary. The UI discloses this
   honestly, but the PS explicitly asks for portal integration; there is not
   even an adapter that *could* go live (no config for credentials, no HTTP).
6. **No explainable evidence viewer (G4).** Evidence is a text list with a page
   number — no PDF render, no bbox highlight, no source span, no "Why?" chain
   from score to rule to document region. This is the most judge-visible
   feature after the portals.
7. **Score inflates unevidenced bidders (G5).** `NOT_VERIFIED = 0.5` ⇒ a bidder
   with zero verified documents scores 50/100. Risky in front of a procurement
   judge: it looks like a half-pass for doing nothing.
8. **EPFO/ESIC rules can never be satisfied (PS item 6).** No schema produces
   `employee_count`/`epfo.status`; they sit at `NOT_VERIFIED` forever. Startup
   India and NSIC (PS item 7) and DigiLocker (PS item 8) are entirely absent.
9. **Contradiction detection is names-only (G5).** No cross-document PAN /
   GSTIN / address / date / figure conflicts — only `entity_resolution.py`
   comparing three legal names.
10. **No audit integrity, no report, no eval, no E2E (G6/G8).** No hash chain or
    verify endpoint, no downloadable PDF report, no `/eval` harness, no
    Playwright E2E, no `docs/DEMO.md`. CI does not run `ruff`, and
    `docker-compose.override.yml` points at a non-existent `next.config.js`.

Runner-up (honesty): **the officer identity in the UI is decorative** —
`bidders/[id]/page.tsx:245` passes the *bidder's* name as `officerName`, so the
header shows the bidder's name as the logged-in officer.

---

## VERDICT: would this survive a 5-minute judge demo?

**No — not in its current default configuration. Not because the engineering is
weak (it is genuinely good), but because a fresh clone does not do what the
problem statement asks.**

What would happen if a judge ran `docker compose up --build` right now:

1. Port 3000 may collide (it did here), and even when it boots, the frontend
   container built from the override runs `npm run dev`, not the production image.
2. The login page rejects everyone: no officer exists until you find and run
   `scripts/create_officer.py`, which is not in the README.
3. With a token, uploading a tender silently produces a **fabricated** tender
   (5.0 cr turnover, 80 cr bid) because Ollama is unreachable from the container.
   Uploading bidder PDFs produces three `unreadable` documents.
4. Evaluation then returns `score 50, HIGH risk, all NOT_VERIFIED` — technically
   honest, visually indistinguishable from "the AI is broken".
5. Everything is readable with no session at all, which a technically-minded
   judge will find within a minute.

What *would* land well, if the above were fixed:

- **Deterministic rule engine with Kleene logic, config-driven rules, legal
  citations and no LLM in the verdict path.** This is the differentiator versus
  teams that let a model decide — it is real, tested (129 tests) and defensible.
- **Honest `NOT_VERIFIED` instead of a fabricated pass**, per-field page +
  confidence provenance, OCR fallback proven on a real image-only PDF.
- **Audit timeline + evidence drawer** that traces a verdict to a document and
  page.
- When Ollama is up, the extraction genuinely works end to end (Run B:
  `score 81`, correct verdicts on real fixture data).

**Minimum bar for demo day, in order:** (a) auth on every route + a working
officer account seeded at boot, (b) a bidder portal with a real submission
flow, (c) LLM reachable from whatever environment is demoed — or an explicit
"extraction unavailable ⇒ NEEDS_REVIEW" screen instead of fabricated
thresholds, (d) a split-screen evidence viewer with the PDF page rendered,
(e) honest per-source status (`VERIFIED / FORMAT_ONLY / UNVERIFIED`) instead of
seeded registries.

**Gap-fill prompts this audit justifies: G1, G2, G4, G5, G6, G7, G8.**
G3 (deterministic rule engine) is **already satisfied** in substance — the
engine exists, is config-driven, is tested and was run twice here; only the
`NOT_VERIFIED` weight and missing rule-mapping coverage need fixing inside it.

---

## Appendix — side effects of this audit (please clean up)

No source files were modified. The following **test data** was written to the
local database and should be deleted before any real demo:

```sql
DELETE FROM audit_events  WHERE tender_id IN (SELECT id FROM tenders WHERE tender_ref LIKE 'AUDIT/%');
DELETE FROM rule_results  WHERE bidder_id IN (SELECT id FROM bidders WHERE name IN ('Audit Bidder A','LLM Bidder A','noauth-probe'));
DELETE FROM documents     WHERE bidder_id IN (SELECT id FROM bidders WHERE name IN ('Audit Bidder A','LLM Bidder A','noauth-probe'));
DELETE FROM requirements  WHERE tender_id IN (SELECT id FROM tenders WHERE tender_ref LIKE 'AUDIT/%');
DELETE FROM decisions     WHERE bidder_id IN (SELECT id FROM bidders WHERE name IN ('LLM Bidder A'));
DELETE FROM verifications WHERE bidder_id IN (SELECT id FROM bidders WHERE name IN ('Audit Bidder A','LLM Bidder A','noauth-probe'));
DELETE FROM bidders       WHERE name IN ('Audit Bidder A','LLM Bidder A','noauth-probe');
DELETE FROM tenders       WHERE tender_ref LIKE 'AUDIT/%';
DELETE FROM officers      WHERE email = 'audit.officer@gov.in';
```

Processes still running from this audit:

| What | Where | Stop with |
|---|---|---|
| Backend (host) | `127.0.0.1:8001` (uvicorn, for Ollama access) | kill the `uvicorn app.main:app` process |
| Backend + Postgres (Docker) | `:8000`, `:5432` | `docker compose down` |
| Frontend probe | `audit-fe` container on `:3005` | `docker rm -f audit-fe` |
| Temp files | `%TEMP%\opencode\` | safe to delete |
