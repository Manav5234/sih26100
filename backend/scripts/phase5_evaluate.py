"""Phase 5 end-to-end: three seeded bidders evaluated by the rule engine
against real stored evidence (Phase 3 extractions + Phase 4 identity check).

  Bidder A: PAN/GST/Udyam all present, names match
  Bidder B: Udyam document missing entirely
  Bidder C: Udyam name conflicts with PAN/GST

Requirements are seeded one-per-rule straight from rules_config.json.
Documents are uploaded through the real API (real OCR + LLM extraction).

Phase 7: seeding is idempotent — stages a bidder has already completed are
skipped, so a plain re-run adds zero documents and zero audit rows. Use
--reset to wipe this tender (and only this tender) and start over.

    python scripts/phase5_evaluate.py [--api http://localhost:8010] [--reset]
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.audit import audit
from app.database import engine
from app.db.models import AuditEvent, Bidder, Document, Requirement, Tender
from app.rule_engine import evaluate_bidder, load_config

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
TENDER_REF = "GEM/2026/T/50001"

DOC_TYPE_BY_FILE = {
    "sample_pan.pdf": "PAN",
    "sample_gst.pdf": "GST",
    "sample_udyam_scanned.pdf": "UDYAM",
    "sample_udyam_tech_solutions.pdf": "UDYAM",
    "sample_financials.pdf": "FINANCIAL",
    "sample_oem_authorization.pdf": "OEM_AUTHORIZATION",
    "sample_local_content.pdf": "LOCAL_CONTENT",
}
BIDDER_DOCS = {
    "A": ["sample_pan.pdf", "sample_gst.pdf", "sample_udyam_scanned.pdf",
          "sample_financials.pdf", "sample_oem_authorization.pdf",
          "sample_local_content.pdf"],
    "B": ["sample_pan.pdf", "sample_gst.pdf"],
    "C": ["sample_pan.pdf", "sample_gst.pdf", "sample_udyam_tech_solutions.pdf"],
}
BIDDER_NAME = "Bidder {key}: ABC Technologies Pvt Ltd"


def reset_seed(db) -> None:
    """Delete this seed tender + its bidders and their audit rows.

    audit_events reference bidders/tenders with ON DELETE SET NULL, so the
    audit rows are removed first — otherwise they linger as orphan events.
    Scoped to TENDER_REF: other tenders are untouched.
    """
    tender = db.query(Tender).filter_by(tender_ref=TENDER_REF).first()
    if tender is None:
        print(f"  nothing to reset ({TENDER_REF} not present)")
        return
    bidder_ids = [b.id for b in db.query(Bidder).filter_by(tender_id=tender.id)]
    audit_q = db.query(AuditEvent).filter(
        or_(AuditEvent.tender_id == tender.id, AuditEvent.bidder_id.in_(bidder_ids)))
    removed_audits = audit_q.delete(synchronize_session=False)
    removed_bidders = (db.query(Bidder).filter_by(tender_id=tender.id)
                       .delete(synchronize_session=False))
    # children (documents, extracted_fields, verifications, rule_results,
    # decisions, requirements) go with ON DELETE CASCADE
    db.query(Tender).filter_by(id=tender.id).delete(synchronize_session=False)
    db.commit()
    print(f"  reset: removed tender {TENDER_REF}, {removed_bidders} bidders, "
          f"{removed_audits} audit rows")


def ensure_tender(db) -> Tender:
    tender = db.query(Tender).filter_by(tender_ref=TENDER_REF).first()
    if tender:
        return tender
    config = load_config()
    tender = Tender(
        id=uuid.uuid4(), tender_ref=TENDER_REF,
        title="Phase 5 Rule Engine Seed Tender",
        minimum_turnover=5.0,              # TURNOVER-001 evaluated (not N/A)
        required_msme_tier=None,           # MSME-CLASS-001 -> NOT_APPLICABLE
        local_content_requirement_applicable=True,
        bid_value_cr=80.0,                 # < 200cr -> LOCAL-CONTENT evaluated
        required_local_content_class="class_2_local_supplier",
        required_oem=None,                 # OEM constraint unspecified
    )
    db.add(tender)
    db.flush()
    for index, rule in enumerate(config["rules"], start=1):
        db.add(Requirement(
            id=uuid.uuid4(), tender_id=tender.id,
            requirement_id=f"REQ-{index:03}",
            title=rule["requirement"], category=rule["category"],
            required_evidence=[], rule_id=rule["rule_id"], status="PENDING",
        ))
    audit(db, "TENDER_UPLOADED", tender_id=tender.id,
          detail={"tender_ref": TENDER_REF, "title": tender.title})
    audit(db, "REQUIREMENTS_EXTRACTED", tender_id=tender.id,
          detail={"requirements": len(config["rules"]),
                  "config_version": config.get("config_version")})
    db.commit()
    return tender


def ensure_bidder(db, tender: Tender, key: str) -> dict:
    """Create the bidder if absent and return its current seed state, so the
    caller only runs the stages that have not run yet."""
    name = BIDDER_NAME.format(key=key)
    bidder = db.query(Bidder).filter_by(tender_id=tender.id, name=name).first()
    if bidder is None:
        bidder = Bidder(id=uuid.uuid4(), tender_id=tender.id, name=name,
                        legal_name="ABC Technologies Pvt Ltd", summary={})
        db.add(bidder)
        db.flush()
        audit(db, "BIDDER_CREATED", tender_id=tender.id, bidder_id=bidder.id,
              detail={"name": name, "key": key})
        db.commit()
    summary = bidder.summary or {}
    docs = {d.doc_type for d in db.query(Document).filter_by(bidder_id=bidder.id)}
    return {"id": str(bidder.id), "name": bidder.name, "docs": docs,
            "identity": summary.get("entity_consistency"),
            "profile": summary.get("profile")}


def pending_stages(docs: set[str], identity, profile,
                   wanted: list[str]) -> dict:
    """Which seed stages still have to run for one bidder — the whole of
    Phase 7's seeding idempotency: nothing already recorded runs twice."""
    return {
        "documents": [f for f in wanted if DOC_TYPE_BY_FILE[f] not in docs],
        "identity": identity is None,
        "evaluate": profile is None,
    }


def upload_documents(client: httpx.Client, info: dict, filenames: list[str]) -> None:
    for filename in filenames:
        path = FIXTURES / filename
        with path.open("rb") as fh:
            resp = client.post(
                f"/bidders/{info['id']}/documents",
                data={"doc_type": DOC_TYPE_BY_FILE[filename]},
                files={"file": (filename, fh, "application/pdf")},
            )
        resp.raise_for_status()


def run_identity_check(client: httpx.Client, info: dict) -> None:
    resp = client.post(f"/bidders/{info['id']}/verify-identity")
    resp.raise_for_status()
    identity = resp.json()
    print(f"  Phase 4 identity: verdict={identity['verdict']} "
          f"outliers={identity['outliers']} missing={identity['missing']}")


def print_results(key: str, info: dict, profile: dict) -> None:
    print(f"\n=== Bidder {key}  ({info['name']})  bidder_id={info['id']}")
    print(f"  {'rule_id':26} {'verdict':15} evidence_refs (paths) / source")
    for res in profile["rule_results"]:
        paths = ",".join(r["path"] for r in res["evidence_refs"]) or "-"
        source = ",".join(res["source"]) or "-"
        print(f"  {res['rule_id']:34} {res['verdict']:15} {paths}  |  src={source}")
    print(f"\n  COMPLIANCE PROFILE: score={profile['score']}  risk={profile['risk']}  "
          f"critical_override_fired={profile['critical_override_fired']}  "
          f"manual_review={profile['manual_review']}")
    print(f"  recommendation: {profile['recommendation']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8010")
    parser.add_argument("--json", action="store_true", help="dump full RuleResults")
    parser.add_argument("--reset", action="store_true",
                        help=f"wipe tender {TENDER_REF} (and its audit rows) first")
    args = parser.parse_args()

    import json as _json

    with Session(engine) as db:
        if args.reset:
            reset_seed(db)
        tender = ensure_tender(db)
        state = {key: ensure_bidder(db, tender, key) for key in BIDDER_DOCS}
        tender_id = str(tender.id)

    with httpx.Client(base_url=args.api, timeout=300.0) as client:
        for key, info in state.items():
            plan = pending_stages(info["docs"], info["identity"],
                                  info["profile"], BIDDER_DOCS[key])
            if plan["documents"]:
                print(f"\n-- Bidder {key}: uploading {len(plan['documents'])} documents")
                upload_documents(client, info, plan["documents"])
            else:
                print(f"\n-- Bidder {key}: documents already uploaded "
                      f"({len(info['docs'])} types) — skipping")
            if plan["identity"]:
                run_identity_check(client, info)
            else:
                print(f"  identity already checked "
                      f"({info['identity']['verdict']}) — skipping")

    for key, info in state.items():
        if info["profile"] is not None:
            print(f"\nBidder {key}: stored compliance profile reused "
                  f"(no re-evaluation, no duplicate audit rows)")
            profile = info["profile"]
        else:
            profile = evaluate_bidder(info["id"], tender_id)
        print_results(key, info, profile)
        if args.json:
            print(_json.dumps(profile, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
