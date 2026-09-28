"""Live check (Phase 7.5, steps d-f): stored audit rows, dashboard, Bidder C.

Run against the already-running server on :8010. Every HTTP call has a
timeout. Exit code 0 only when every check passes.

  d) TENDER_UPLOADED / REQUIREMENTS_EXTRACTED for the API-uploaded tender
     carry extraction_method (tender-level audit rows are exposed by no read
     endpoint, so they are read straight from audit_events — read-only).
  e) GET /dashboard reports count == 3.
  f) Bidder C: evaluate, then profile — score 65, risk HIGH, critical
     override, ENTITY-CONSISTENCY-001 CONFLICT with the UDYAM outlier,
     evidence refs carrying filename/page/confidence, demo_notice present.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

BASE = "http://localhost:8010"
API_TENDER_REF = os.environ.get("TENDER_REF", "GEM/2026/T/50005")
SEED_TENDER_REF = "GEM/2026/T/50001"      # readable through Bidder C's timeline
DEMO_NOTICE = ("Demo Environment: government-source results are simulated "
               "via mock adapters")
TENDER_STAGES = ("TENDER_UPLOADED", "REQUIREMENTS_EXTRACTED")

checks: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    checks.append((name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")
    return bool(ok)


def _tender_id(ref: str) -> str | None:
    r = requests.get(f"{BASE}/tenders", timeout=10)
    if r.status_code != 200:
        return None
    tender = next((t for t in r.json().get("tenders", [])
                   if t.get("tender_ref") == ref), None)
    return tender["id"] if tender else None


def _audit_rows(tender_id: str) -> dict:
    """event_type -> payload. Read-only: no HTTP endpoint exposes
    tender-level audit rows."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sqlalchemy import create_engine, text

    from app.config import settings

    with create_engine(settings.database_url).connect() as conn:
        return dict(conn.execute(text(
            "SELECT event_type, payload FROM audit_events "
            "WHERE tender_id = :t ORDER BY created_at"),
            {"t": tender_id}).all())


def main() -> int:
    # a) login (reads are open, but evaluate needs the JWT)
    r = requests.post(f"{BASE}/auth/login", json={
        "email": "priya@example.gov.in", "password": "secret123"}, timeout=10)
    check("Login", r.status_code == 200, f"HTTP {r.status_code}")
    token = r.json().get("token") or ""
    check("JWT issued", bool(token))
    hdrs = {"Authorization": f"Bearer {token}"}

    # --- d) audit rows of the API-uploaded tender ---------------------------
    print(f"\n--- d) audit rows ({API_TENDER_REF}) ---")
    api_tender_id = _tender_id(API_TENDER_REF)
    check(f"tender {API_TENDER_REF} listed", api_tender_id is not None)
    rows: dict = _audit_rows(api_tender_id) if api_tender_id else {}
    for stage in TENDER_STAGES:
        payload = rows.get(stage) or {}
        check(f"{stage} audit row present", stage in rows)
        check(f"{stage} detail contains extraction_method",
              bool(payload.get("extraction_method")),
              repr(payload.get("extraction_method")))

    seed_id = _tender_id(SEED_TENDER_REF)
    seed_rows = _audit_rows(seed_id) if seed_id else {}
    seed_missing = [s for s in TENDER_STAGES
                    if not (seed_rows.get(s) or {}).get("extraction_method")]
    if seed_missing:
        # informational only: those rows were written by the Phase 5 seed
        # script, which never wrote the field — not a POST /tenders/upload row.
        print(f"[flag] tender {SEED_TENDER_REF} seed audit rows predate "
              f"extraction_method: {', '.join(seed_missing)} "
              "(written by phase5_evaluate.py, not the upload endpoint)")

    # --- e) dashboard -------------------------------------------------------
    print("\n--- e) dashboard ---")
    r = requests.get(f"{BASE}/dashboard", timeout=10)
    check("GET /dashboard HTTP 200", r.status_code == 200, f"HTTP {r.status_code}")
    dash = r.json() if r.status_code == 200 else {"bidders": [], "count": -1}
    check("dashboard count == 3", dash.get("count") == 3, str(dash.get("count")))

    bidder_c = next((b for b in dash.get("bidders", [])
                     if str(b.get("name", "")).startswith("Bidder C")), None)
    check("Bidder C on dashboard", bidder_c is not None,
          bidder_c.get("name") if bidder_c else "missing")
    if not bidder_c:
        _summary()
        return 1
    bidder_id = bidder_c["bidder_id"]

    # --- f) Bidder C: evaluate then profile ---------------------------------
    print("\n--- f) Bidder C evaluate + profile ---")
    r = requests.post(f"{BASE}/bidders/{bidder_id}/evaluate",
                      headers=hdrs, timeout=60)
    check("POST /bidders/{id}/evaluate HTTP 200", r.status_code == 200,
          f"HTTP {r.status_code}")
    if r.status_code != 200:
        print(r.text[:300])

    r = requests.get(f"{BASE}/bidders/{bidder_id}/profile", timeout=10)
    check("GET /bidders/{id}/profile HTTP 200", r.status_code == 200,
          f"HTTP {r.status_code}")
    profile = r.json() if r.status_code == 200 else {}

    check("score == 65", profile.get("score") == 65, str(profile.get("score")))
    check("risk == HIGH", profile.get("risk") == "HIGH",
          repr(profile.get("risk")))
    check("critical_override_fired is True",
          profile.get("critical_override_fired") is True,
          repr(profile.get("critical_override_fired")))
    check("demo_notice present", bool(profile.get("demo_notice")),
          repr(profile.get("demo_notice")))
    check("demo_notice matches the platform notice",
          profile.get("demo_notice") == DEMO_NOTICE,
          repr(profile.get("demo_notice")))

    results = profile.get("rule_results") or []
    check("rule_results cover every configured rule",
          len(results) == _rule_count(), f"{len(results)}/{_rule_count()}")
    entity = next((x for x in results
                   if x.get("rule_id") == "ENTITY-CONSISTENCY-001"), None)
    check("ENTITY-CONSISTENCY-001 present", entity is not None)
    if entity:
        check("ENTITY-CONSISTENCY-001 verdict == CONFLICT",
              entity.get("verdict") == "CONFLICT", repr(entity.get("verdict")))
        consistency = entity.get("entity_consistency") or {}
        outliers = consistency.get("outliers") or []
        check("outliers == ['UDYAM']", outliers == ["UDYAM"], str(outliers))
        names = set((consistency.get("names") or {}).keys())
        check("names compared across PAN/GST/UDYAM",
              names == {"PAN", "GST", "UDYAM"}, str(sorted(names)))

    # evidence drawer refs: filename, page, confidence on every doc-derived ref
    doc_refs = [ref for x in results for ref in (x.get("evidence_refs") or [])
                if ref.get("origin") in ("document", "derived")]
    check("document evidence refs exist", bool(doc_refs), f"{len(doc_refs)} refs")
    bad = [f"{k}:{x.get(k)!r}" for x in doc_refs
           for k in ("document_filename", "page", "confidence")
           if x.get(k) is None or x.get(k) == ""]
    no_conf = [str(x.get("document_filename")) for x in doc_refs
               if isinstance(x.get("confidence"), (int, float))
               and x["confidence"] <= 0]
    check("every evidence ref has filename, page and confidence",
          not bad and not no_conf,
          f"{len(bad) + len(no_conf)} bad of {len(doc_refs)}")

    return _summary()


def _rule_count() -> int:
    import json

    rules = Path(__file__).resolve().parent.parent / "app" / "config" / "rules_config.json"
    return len(json.loads(rules.read_text(encoding="utf-8"))["rules"])


def _summary() -> int:
    print("\n--- Checks ---")
    for name, ok, detail in checks:
        print(f"{name}: {'PASS' if ok else 'FAIL'}"
              f"{(' | ' + detail) if detail else ''}")
    failed = [name for name, ok, _ in checks if not ok]
    print(f"\nRESULT: {'PASS' if not failed else 'FAIL'} "
          f"({len(checks) - len(failed)}/{len(checks)})")
    if failed:
        print("failed: " + "; ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
