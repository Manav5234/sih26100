# HANDOFF.md — SIH26100 Bid Compliance Verification Platform

Status: **Phases 1–7.5 complete and tested (129 backend tests green).** Phase 8
(officer dashboard UI) is next, awaiting approval.

## Hard project rules (never break these)

1. **No real government APIs.** All registry checks go through
   `GovernmentSourceAdapter` mocks. The UI carries
   `Demo Notice`: "Demo Environment — results simulated via mock adapter"
   (`frontend/src/components/ui/DemoNotice.tsx`) so the product never implies
   live GSTN/Udyam/PAN access.
2. **The LLM never decides.** It extracts fields (strict JSON, temperature 0)
   and is never asked for a verdict, score, or recommendation. Verdicts come
   from the deterministic rule engine; the recommendation is a template over
   verdicts; only a Procurement Officer records a final decision.
3. **Null over guessing.** Anything not fully legible/parsable becomes `null`
   (`KEY_FORMATS` rejects truncated IDs; `_number()` rejects unparseable
   amounts). A partial identifier is never stored as evidence.
4. **Missing evidence → `NOT_VERIFIED`, never `VIOLATION`.** Kleene three-valued
   logic: absent data makes a condition UNKNOWN, and UNKNOWN resolves to the
   rule's `on_source_unreachable` verdict (default `NOT_VERIFIED`).

## Phase map

| Phase | What landed | Key files |
|---|---|---|
| 1 | Repo stripped of prior domain, SIH26100/BidVerify identity | repo-wide |
| — | Schema: 11 tables, squashed migration applied | `app/db/models.py`, `alembic/versions/0001_initial.py` |
| 3 | Document intelligence: text-layer → OCR (rapidocr) → LLM strict-JSON extraction | `app/extraction.py`, `app/ocr.py`, `app/llm.py`, `app/main.py` |
| 4 | Entity-name normalization + cross-document identity comparison, stored on bidder | `app/entity_resolution.py`, `POST /bidders/{id}/verify-identity` |
| 5 | Config-driven rule engine, 13 rules | `app/rule_engine.py`, `tests/test_rule_engine.py` |
| 6 | Score / risk / recommendation from config scoring block | `calculate_score`, `calculate_risk`, `generate_recommendation` in `app/rule_engine.py` |
| 6.5 | Mock government-source adapters, statuses + audit rows | `app/adapters.py`, `verifications` table |
| 6.7 | Financial / OEM / local-content extraction → TURNOVER, OEM-AUTH, LOCAL-CONTENT rules | `DOC_SCHEMAS` in `app/extraction.py`, `_BIDDER_NUMERIC_FIELDS` in `app/rule_engine.py` |
| 7 | Persisted submission record, audit trail, dashboard + audit APIs | `app/audit.py`, `evaluate_bidder` in `app/rule_engine.py`, `GET /dashboard`, `GET /bidders/{id}/audit`, `POST /bidders/{id}/decisions`, `tests/test_phase7.py` |
| 7.5 | Tender upload API (LLM extraction + template fallback), requirements read, evaluate + profile endpoints | `app/tender_extraction.py`, `app/schemas/tender.py`, routes in `app/main.py`, `tests/test_phase75.py` |

## `rules_config.json` (backend/app/config/, v1.1.0)

Read fresh from disk at every evaluation — thresholds and conditions are
**never** hardcoded in application code.

Structure:

- `config_version`, `last_verified`, `verdicts[]`, `note`
- `rules[13]`, each with: `rule_id`, `requirement`, `category`, `source`
  (legal citation), `condition`, `pass`, `fail`, and optionally:
  - `not_applicable_when` — applicability guard, evaluated first
  - `classification` (+ `class_order`) — data-driven `classify()` tiers
  - `on_source_unreachable` — verdict when evidence is missing
  - `tender_override_allowed` — threshold must be re-read from the tender
  - `notes` / `warning`
- `critical_override_rule_ids`: `["DEBARMENT-001", "ENTITY-CONSISTENCY-001"]`
  — **the single source of truth** for critical overrides (an inline
  `critical_override: true` field on DEBARMENT-001 was dropped in the review
  round so the two could never drift apart)
- `scoring`: `weights` (NA = `excluded_from_denominator`), `formula`,
  `risk_bands` (LOW ≥ 85, MEDIUM 60–84, HIGH < 60 **or** any critical override)

### The four fixes, v1.0.0 → v1.1.0 (review round, before Phase 2)

1. **LOCAL-CONTENT-001**: `fail` was `NOT_APPLICABLE` — a non-local bidder
   silently fell out of the score denominator instead of being penalized.
   Fixed to `fail: VIOLATION`, restructured as classify-then-compare against
   `tender.required_local_content_class`, with `not_applicable_when` covering
   the two cases the rule genuinely doesn't bind (Make-in-India preference not
   invoked, or `bid_value_cr >= 200`).
2. **OEM-AUTH-001**: notes said "NOT_APPLICABLE when bidder is itself the OEM"
   but there was no field to express it. Added
   `not_applicable_when: "bidder.is_oem == true"`.
3. **TURNOVER-001**: no NA path for tenders with no minimum turnover — the
   condition was unevaluable. Added
   `not_applicable_when: "tender.minimum_turnover is null"`.
4. **MSME-CLASS-001**: condition only classified the bidder (micro/small/medium)
   without comparing to the tender. Added comparison against a new
   `tender.required_msme_tier` field, plus `not_applicable_when` when the
   tender doesn't restrict by tier.

Later, separate fix (Phase 5): `class_order` added to LOCAL-CONTENT-001 so the
`meets or exceeds` comparison from fix #1 has an ordinal ranking to use.

## Rule engine evaluation order (`evaluate_rule`)

For each tender requirement → one RuleResult, in this order:

1. **(a) `not_applicable_when`** → if true, verdict `NOT_APPLICABLE` (condition
   never evaluated).
2. **(b/c) condition parse special cases**: starts with `N/A` → informational,
   verdict from `pass`. `IF guard THEN body`: guard false → `NOT_APPLICABLE`;
   guard unknown → `on_source_unreachable`.
3. **(d) evaluate with Kleene logic**: result UNKNOWN (any missing operand) →
   `on_source_unreachable` (default `NOT_VERIFIED`).
4. **(e)** true → `pass` verdict; false → `fail` verdict.

Engine vocabulary: `== != > >= < <= AND OR is null is not null is in matches
"meets or exceeds"`, functions `classify()` (tiers from the rule's own
`classification` block) and `normalize()` (Phase 4 name normalization).
`matches` with an unspecified (null) right side returns true — "(if specified)"
semantics. Score = config weights, NA excluded from numerator and denominator;
all-NA → score `null` + manual review. Risk bands are evaluated in config
order, first match wins; LOW/MEDIUM both require no critical override, so
`critical_override_rule_ids` always beats a good score. Recommendation text is
a template over verdicts + requirement strings — never an LLM call.

Special wiring (data plumbing, not business logic): `ENTITY-CONSISTENCY-001`
reads Phase 4's stored comparison; `pan.format_valid` is derived with the same
`KEY_FORMATS` check Phase 3 uses; `bidder.turnover` / `local_content_pct` come
from Phase 6.7 documents; registry statuses come from adapters.

## Mock adapter pattern (`app/adapters.py`)

```python
class GovernmentSourceAdapter(ABC):
    source: str
    def verify(self, identifier: str) -> dict:
        # {status, matched_fields, source, confidence}
```

- `MockPANAdapter` → `VALID`, `MockGSTAdapter` → `ACTIVE`,
  `MockUdyamAdapter` → `ACTIVE`, `MockDebarmentAdapter` (keyed by PAN) →
  `NOT_DEBARRED`. Registries are seeded with the fixture identifiers only.
- **Unknown identifier → `NOT_VERIFIED`, confidence 0.0** — the mock never
  fabricates a pass; the attempt is still recorded as `NOT_FOUND`.
- **No extracted identifier → the adapter is never called** (B: Udyam document
  missing; A: formerly-redacted number). Status stays null and the rule stays
  `NOT_VERIFIED` *because evidence is missing*, not because of a fake failure.
- Wiring lives in `build_bidder_evidence()`; every call is audited into the
  `verifications` table (`MATCHED`/`NOT_FOUND` + full response payload).
- `gst.status` is adapter-sourced, not read from the "Status: Active" line
  printed on the uploaded certificate (that line was the Phase 6.5 finding —
  fixture text was silently acting as registry truth).

## Phase 7: persistence + audit trail (`app/audit.py`)

`audit(db, stage, tender_id=, bidder_id=, detail=, actor=)` queues one
`audit_events` row on the caller's session (caller commits). Storage maps the
spec's `{bidder_id, tender_id, stage, detail, timestamp}` onto the existing
table: `event_type`=stage, `payload`=detail, `created_at`=timestamp. Append-only
stage vocabulary is documented in `app/audit.py`.

Stages, in pipeline order:

| stage | written by |
|---|---|
| `TENDER_UPLOADED`, `REQUIREMENTS_EXTRACTED` | `ensure_tender` (seeder) **and** `POST /tenders/upload` |
| `BIDDER_CREATED` | `POST /bidders`, seeder |
| `DOCUMENT_UPLOADED`, `OCR_COMPLETED` (only when method=`ocr`), `FIELDS_EXTRACTED` | `POST /bidders/{id}/documents` |
| `SOURCE_CHECKED` | one per adapter call in `_verify_via_adapters` |
| `ENTITY_CONSISTENCY_CHECK` | `POST /bidders/{id}/verify-identity` |
| `RULES_EVALUATED` (+ `CONFLICT_DETECTED` when any VIOLATION/CONFLICT) | `evaluate_bidder` |
| `OFFICER_DECISION_RECORDED` | `POST /bidders/{id}/decisions` (actor = officer name) |

**Stored submission record.** `evaluate_bidder` now, in one transaction:
deletes the bidder's existing `rule_results` rows (re-evaluation *replaces*,
never appends — one RuleResult set per bidder), inserts one row per requirement
(`rule_id`, `verdict`, `evidence` refs), and writes
`bidders.summary = {entity_consistency…, profile: <full profile>, evaluated_at}`.
The dashboard reads `summary.profile`; nothing is recomputed per page load.
Returned profile keys are unchanged (tests assert the exact set).

**Endpoints.** `GET /dashboard` → every bidder across tenders with
`score, risk, status, pending_review, recommendation, evaluated_at`;
`status` = latest decision, else `AWAITING_DECISION` / `AWAITING_EVALUATION`;
`pending_review` = undecided **and** (unevaluated or flagged manual review).
`GET /bidders/{id}/audit` → that bidder's events **plus** the tender-level
events (tender upload, requirements) in `created_at` order.

**Evidence trail now carries `confidence`** (hard rule 5) on every
document-derived ref and on identity `page_refs`; the legal citation was already
stored per result as `legal_citation`.

**Idempotent seeding.** `phase5_evaluate.py` skips any stage already recorded
(`pending_stages()` — documents by doc_type, identity by
`summary.entity_consistency`, evaluation by `summary.profile`) and re-prints the
*stored* profile instead of re-evaluating. Re-run → 0 new audit rows, 0 new
documents, 0 new rule_results. `--reset` wipes tender `GEM/2026/T/50001` and its
audit rows first (audit FKs are `ON DELETE SET NULL`, so audit rows are deleted
before the tender).

Two fixes that fell out of persisting the profile: `_tender_dict` converts
`Numeric`/`Decimal` → `float` (JSONB could not serialize `Decimal`), and
`zip(requirements, results, strict=True)` guards the 1:1 requirement↔result map.

## Phase 7.5: the missing API surface (`app/main.py` + `app/tender_extraction.py`)

| method | path | decorator (file: `app/main.py`) |
|---|---|---|
| POST | `/tenders/upload` | `@app.post("/tenders/upload", response_model=TenderDetailOut)` |
| GET | `/tenders` | `@app.get("/tenders", response_model=TenderListResponse)` |
| GET | `/tenders/{tender_id}/requirements` | `@app.get("/tenders/{tender_id}/requirements", response_model=RequirementListResponse)` |
| POST | `/bidders/{bidder_id}/evaluate` | `@app.post("/bidders/{bidder_id}/evaluate")` |
| GET | `/bidders/{bidder_id}/profile` | `@app.get("/bidders/{bidder_id}/profile", response_model=ComplianceProfileOut)` |

**Auth.** The two mutating officer actions (`/tenders/upload`,
`/bidders/{id}/evaluate`) use the existing
`Depends(get_current_officer)` JWT guard, same as `POST /bidders/{id}/decisions`.
The three GETs stay open, like `GET /dashboard` and `GET /bidders/{id}/audit`.

**Upload pipeline** (`app/tender_extraction.py`): PDF → `read_pages()`
(text layer → OCR fallback, the bidder-document pipeline) → one
`llm.extract_json` call keyed `["tender_fields", "requirements"]` → validation
against `rules_config.json`.

- `tender_fields` = the Phase 2 six (`minimum_turnover`, `required_msme_tier`,
  `local_content_requirement_applicable`, `required_local_content_class`,
  `bid_value_cr`, `required_oem`), each nulled unless fully parseable
  (`_number`, tier/class whitelists taken from the config's own
  `classification` / `class_order`).
- `requirements[]` = title, category, source_clause, required_evidence,
  matches_rule. **Every `matches_rule` is checked against the config's rule
  ids; invalid, missing and duplicate mappings are dropped** (never stored,
  never invented) — `Requirement.rule_id` has no NULL path.
- **Fallback:** LLM error/timeout, or zero surviving requirements → the
  controlled template (one requirement per configured rule = the seeded
  13-requirement set, plus the seed tender's thresholds 5.0 cr / 80 cr /
  class_2) and `extraction_method = "template_fallback"` instead of `"llm"`.
  The value is on the response **and** on both audit rows, so the demo can
  never die on extraction and never claims the LLM ran when it didn't.
- Audit rows `TENDER_UPLOADED` + `REQUIREMENTS_EXTRACTED` are written by
  this endpoint in the same transaction (detail includes `extraction_method`
  and the requirement count).

**Reads.** `GET /tenders` lists tenders with `requirement_count`;
`GET /tenders/{id}/requirements` returns each requirement joined with
`rule: {rule_id, requirement, source, last_verified}` straight from
`rules_config.json`.

**Evaluate.** Thin wrapper over `evaluate_bidder` (existing behaviour):
replaces `rule_results` (one set per bidder), stores `summary.profile`,
writes exactly one `RULES_EVALUATED` per run. Returns the full profile.

**Profile** (`GET /bidders/{id}/profile`) reads the stored record (404 until
evaluated) and returns score, risk, `critical_override_fired`, recommendation,
`manual_review`, the newest `decision` (if any), and `rule_results[]` with
`rule_id`, the config `requirement` text, verdict, `legal_citation`, and
`evidence_refs` enriched with `document_filename` (original filename from the
`DOCUMENT_UPLOADED` audit payload, falling back to the stored path basename),
`page`, `value`, `confidence` and `source` (adapter name for registry checks).
`ENTITY-CONSISTENCY-001` additionally carries
`entity_consistency = {verdict, names: {PAN, GST, UDYAM: {name, normalized}},
outliers, missing}`. Every response ends with
`demo_notice = "Demo Environment: government-source results are simulated via mock adapters"`.

**Sample tender.** `python scripts/make_sample_docs.py` also writes
`tests/fixtures/sample_tender.pdf` (3-page digital RFP): clauses 1.1/2.1–2.4/
3.1/4.1/5.1/6.1/7.1 map to bid value, PAN, GST, Udyam, entity consistency,
turnover 5 cr, OEM (Siemens), local content Class-2 and debarment.

## Seeded demo bidders (final, `scripts/phase5_evaluate.py`)

Tender `GEM/2026/T/50001`: minimum_turnover 5.0 cr, local content required
(class_2), bid 80 cr, no MSME-tier restriction, no OEM named.

| | A | B | C |
|---|---|---|---|
| Documents | PAN, GST, Udyam (scanned), financials, OEM letter, local content | PAN, GST | PAN, GST, Udyam (conflicting name) |
| Identity (Phase 4) | MATCH | NOT_VERIFIED (no Udyam) | **CONFLICT** |
| Score | **90** | **65** | **65** |
| Risk | **LOW** | **MEDIUM** | **HIGH** (`critical_override_fired=True`) |
| Manual review | no | yes | yes |
| SATISFIED (8) | PAN, GST, UDYAM, ENTITY, TURNOVER, LOCAL-CONTENT, OEM, DEBARMENT | PAN, GST, DEBARMENT | PAN, GST, UDYAM, DEBARMENT |
| NOT_VERIFIED (2) | EPFO, ESIC (`bidder.employee_count` null — labour deferred) | 7 rules (no Udyam/identity/financial/OEM docs) | 5 rules |
| NOT_APPLICABLE (3, excluded) | GST-002, MSME-CLASS, MSE-PURCHASE-PREF (same for all three) | | |

B and C tie at 65 **on purpose**: identical raw scores with different risk
demonstrates that `critical_override_rule_ids` — not the number — decides risk
(C's ENTITY-CONFLICT override forces HIGH while B sits at MEDIUM).

## Running it

```bash
# backend tests (129 passing)
cd backend && python -m pytest -q

# regenerate the 8 sample PDFs (7 bidder docs + sample_tender.pdf)
python scripts/make_sample_docs.py

# settings — backend/.env is loaded automatically (its path comes from
# app/config.py, not the shell), so no env vars are needed. Real env vars
# still win, so docker-compose/CI overrides are unaffected.

# API on :8010, one command from any terminal
.\backend\scripts\dev_up.ps1             # frees port 8010 if busy, Ctrl+C stops
# (or manually: cd backend && python -m uvicorn app.main:app --port 8010)
# the first two log lines are the startup health check: DB target (password
# masked) and whether the LLM answers — a warning there explains a later
# template_fallback extraction.

# officer login (idempotent: re-running prints "already exists", exit 0)
python scripts/create_officer.py --name "Priya Sharma" \
  --email priya@example.gov.in --password secret123 --role inspector
# unreachable DB prints one line with the host it tried, not a traceback

# end-to-end: seed bidders, upload docs, identity check, full profiles
python scripts/phase5_evaluate.py            # idempotent: skips what exists
python scripts/phase5_evaluate.py --reset    # wipe this tender, re-seed clean

# read the stored record (no recompute)
curl http://localhost:8010/dashboard
curl http://localhost:8010/bidders/{id}/audit

# Phase 7.5 — upload / read a tender, evaluate, read the profile.
# upload + evaluate are JWT-guarded; login first and reuse $TOKEN.
TOKEN=$(curl -s -m 10 -X POST http://localhost:8010/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"...","password":"..."}' | python -c "import sys,json;print(json.load(sys.stdin)['token'])")

curl -m 30 -X POST http://localhost:8010/tenders/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@tests/fixtures/sample_tender.pdf;type=application/pdf" \
  -F "tender_ref=GEM/2026/T/50002" \
  -F "title=Signalling equipment supply"

curl -m 10 http://localhost:8010/tenders
curl -m 10 http://localhost:8010/tenders/{tender_id}/requirements

curl -m 60 -X POST http://localhost:8010/bidders/{bidder_id}/evaluate \
  -H "Authorization: Bearer $TOKEN"
curl -m 10 http://localhost:8010/bidders/{bidder_id}/profile
```

## Deferred / next

- **Phase 8 (next):** officer dashboard **UI** (list from `GET /dashboard`,
  timeline from `GET /bidders/{id}/audit`, decision form →
  `POST /bidders/{id}/decisions`, tender upload + requirements from
  `POST /tenders/upload` / `GET /tenders/{id}/requirements`, evidence drawer
  from `GET /bidders/{id}/profile`) — mount `DemoNotice` beside every status
  display. Backend APIs exist; frontend has no dashboard page yet.
- Labour rules (EPFO/ESIC): need `bidder.employee_count` evidence.
- Debarred-bidder scenario (4th bidder) to demo the override end-to-end in UI.
- Frontend has no `node_modules` in this environment — lint/typecheck was not
  run; run `npm ci && npm run lint` before the next frontend change.
