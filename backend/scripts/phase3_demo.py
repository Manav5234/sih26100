"""Phase 3 end-to-end demo: seed tender + bidder, upload the three sample
documents through the real API, print the extracted evidence.

    python scripts/phase3_demo.py [--api http://localhost:8010]
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx
from sqlalchemy.orm import Session

from app.database import engine
from app.db.models import Bidder, Tender

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
DOCS = [
    ("PAN", "sample_pan.pdf"),
    ("GST", "sample_gst.pdf"),
    ("UDYAM", "sample_udyam_scanned.pdf"),
]
TENDER_REF = "GEM/2026/T/00456"


def ensure_tender_and_bidder() -> tuple[str, str]:
    with Session(engine) as db:
        tender = db.query(Tender).filter_by(tender_ref=TENDER_REF).first()
        if not tender:
            tender = Tender(id=uuid.uuid4(), tender_ref=TENDER_REF,
                            title="ABC Equipment Procurement")
            db.add(tender)
            db.flush()
        bidder = db.query(Bidder).filter_by(tender_id=tender.id).first()
        if not bidder:
            bidder = Bidder(id=uuid.uuid4(), tender_id=tender.id,
                            name="ABC Technologies Pvt Ltd",
                            legal_name="ABC Technologies Pvt Ltd")
            db.add(bidder)
        db.commit()
        return str(tender.id), str(bidder.id)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8010")
    args = parser.parse_args()

    tender_id, bidder_id = ensure_tender_and_bidder()
    print(f"tender_id  = {tender_id}")
    print(f"bidder_id  = {bidder_id}\n")

    with httpx.Client(base_url=args.api, timeout=300.0) as client:
        for doc_type, filename in DOCS:
            path = FIXTURES / filename
            with path.open("rb") as fh:
                resp = client.post(
                    f"/bidders/{bidder_id}/documents",
                    data={"doc_type": doc_type},
                    files={"file": (filename, fh, "application/pdf")},
                )
            if resp.status_code != 200:
                print(f"UPLOAD FAILED {doc_type}: {resp.status_code} {resp.text}")
                return 1
            body = resp.json()
            print(f"--- {doc_type} ({filename})")
            print(f"    status={body['status']}  extraction_method={body['extraction_method']}")
            for f in body["fields"]:
                print(f"    {f['field_name']:18} = {f['value']!r:45} "
                      f"conf={f['confidence']:.2f} page={f['page']} "
                      f"via={f['extraction_method']}")
            print()

        listing = client.get(f"/bidders/{bidder_id}/documents")
        print("=== GET /bidders/{}/documents ===".format(bidder_id))
        for d in listing.json()["documents"]:
            print(f"  {d['doc_type']:8} status={d['status']:11} "
                  f"method={d['extraction_method'] or '-'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
