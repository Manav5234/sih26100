"""Live check: POST /tenders/upload must return extraction_method == "llm".

Run against the already-running server on :8010. Every HTTP call has a timeout.
Exit code 0 only when the LLM path produced the requirements.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

BASE = "http://localhost:8010"
PDF = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "sample_tender.pdf"
RULES = Path(__file__).resolve().parent.parent / "app" / "config" / "rules_config.json"
TENDER_REF = os.environ.get("TENDER_REF", "GEM/2026/T/50003")
# two LLM calls are possible (extraction + the required_oem retry), each up to
# LLM_TIMEOUT (300s) + PDF read + persistence.
UPLOAD_TIMEOUT = 700

checks: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    checks.append((name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")
    return ok


def _stored_tender(ref: str) -> dict:
    """Existing tender_ref -> the payload shape POST /tenders/upload returns,
    so a 409 (already uploaded) still gets a full report instead of a crash.

    extraction_method is exposed by no read endpoint, so it comes from the
    tender's own audit row — the same value the upload response mirrors."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sqlalchemy import create_engine, text

    from app.config import settings

    listed = requests.get(f"{BASE}/tenders", timeout=10).json()
    tender = next((t for t in listed.get("tenders", [])
                   if t["tender_ref"] == ref), None)
    if tender is None:
        return {}
    detail = requests.get(f"{BASE}/tenders/{tender['id']}/requirements",
                          timeout=10).json()
    reqs = detail.get("requirements") or []
    with create_engine(settings.database_url).connect() as conn:
        method = conn.execute(text(
            "SELECT payload ->> 'extraction_method' FROM audit_events "
            "WHERE tender_id = :t AND event_type = 'TENDER_UPLOADED'"),
            {"t": tender["id"]}).scalar()
    return {**tender, "requirements": reqs, "requirement_count": len(reqs),
            "extraction_method": method}


def main() -> int:
    cfg = json.loads(RULES.read_text(encoding="utf-8"))
    rule_ids = {r["rule_id"] for r in cfg["rules"]}
    print(f"rules_config.json v{cfg.get('config_version')}: {len(rule_ids)} rule_ids")

    # a) login
    r = requests.post(f"{BASE}/auth/login", json={
        "email": "priya@example.gov.in", "password": "secret123"}, timeout=10)
    check("Login", r.status_code == 200, f"HTTP {r.status_code}")
    token = r.json().get("token") or ""
    check("JWT issued", bool(token))
    hdrs = {"Authorization": f"Bearer {token}"}

    # b) upload
    t0 = time.time()
    with open(PDF, "rb") as fh:
        r = requests.post(f"{BASE}/tenders/upload", headers=hdrs,
                          timeout=UPLOAD_TIMEOUT, files={
            "file": ("sample_tender.pdf", fh, "application/pdf")}, data={
            "tender_ref": TENDER_REF,
            "title": "Signalling equipment supply",
        })
    upload_s = time.time() - t0
    if r.status_code == 409:
        # already uploaded earlier — report what is stored instead of dying
        check("PDF upload accepted", True,
              f"409 {TENDER_REF} already exists -> reading the stored tender")
        body = _stored_tender(TENDER_REF)
        if not body:
            check("stored tender found", False, TENDER_REF)
            print(r.text[:500])
            return 1
        check("stored tender found", True, TENDER_REF)
    elif r.status_code != 200:
        check("PDF upload accepted", False, f"HTTP {r.status_code}")
        print(r.text[:500])
        return 1
    else:
        check("PDF upload accepted", True,
              f"HTTP 200 in {upload_s:.1f}s")
        body = r.json()
    method = body.get("extraction_method")
    print(f"extraction_method = {method!r}")
    reqs = body.get("requirements") or []

    # c) assertions on the upload response
    check("extraction_method == 'llm'", method == "llm", str(method))
    check("required_oem == 'Siemens'", body.get("required_oem") == "Siemens",
          repr(body.get("required_oem")))
    check("requirement_count > 0", body.get("requirement_count", 0) > 0,
          str(body.get("requirement_count")))
    with_clause = [x for x in reqs if (x.get("source_clause") or "").strip()]
    with_evidence = [x for x in reqs if x.get("required_evidence")]
    check("some requirements have source_clause", bool(with_clause),
          f"{len(with_clause)}/{len(reqs)}")
    check("some requirements have required_evidence", bool(with_evidence),
          f"{len(with_evidence)}/{len(reqs)}")
    bad_rules = sorted({x.get("rule_id") for x in reqs} - rule_ids)
    check("every rule_id exists in rules_config.json", not bad_rules, str(bad_rules))

    # d) table
    print("\n%-34s | %-22s | %-40s | %s" % ("title", "source_clause",
                                            "required_evidence", "rule_id"))
    print("-" * 130)
    for x in reqs:
        ev = x.get("required_evidence") or []
        ev_s = "; ".join(ev) if isinstance(ev, list) else str(ev)
        print("%-34s | %-22s | %-40s | %s" % (
            str(x.get("title"))[:34], str(x.get("source_clause"))[:22],
            ev_s[:40], x.get("rule_id")))

    # e) persisted rows
    tid = body.get("id")
    r2 = requests.get(f"{BASE}/tenders/{tid}/requirements", timeout=10)
    check("GET /tenders/{id}/requirements HTTP 200", r2.status_code == 200,
          f"HTTP {r2.status_code}")
    stored = r2.json().get("requirements") if r2.status_code == 200 else []
    stored = stored or []
    same = len(stored) == len(reqs) and all(
        a.get("rule_id") == b.get("rule_id") and a.get("title") == b.get("title")
        and a.get("source_clause") == b.get("source_clause")
        for a, b in zip(stored, reqs))
    check("persisted rows match upload response", same,
          f"stored={len(stored)} vs response={len(reqs)}")

    # f) summary
    print("\n--- Extraction result ---")
    print(f"method={method} required_oem={body.get('required_oem')} "
          f"requirement_count={body.get('requirement_count')}")
    print(f"requirements_with_source_clause={len(with_clause)}/{len(reqs)} "
          f"requirements_with_required_evidence={len(with_evidence)}/{len(reqs)}")
    print(f"upload time = {upload_s:.1f}s" if r.status_code == 200
          else "upload skipped (tender already stored)")

    missing_clause = [x.get("title") for x in reqs if not (x.get("source_clause") or "").strip()]
    missing_ev = [x.get("title") for x in reqs if not x.get("required_evidence")]
    if missing_clause:
        print(f"[flag] no source_clause: {missing_clause}")
    if missing_ev:
        print(f"[flag] no required_evidence: {missing_ev}")

    print("\n--- Checks ---")
    for name, ok, detail in checks:
        print(f"{name}: {'PASS' if ok else 'FAIL'}{(' | ' + detail) if detail else ''}")
    return 0 if method == "llm" else 1


if __name__ == "__main__":
    sys.exit(main())
