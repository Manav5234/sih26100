"""Generate the Phase 3/6.7 sample bidder documents.

  sample_pan.pdf                  clean digital PDF with a real text layer
  sample_gst.pdf                  clean digital PDF with a real text layer
  sample_udyam_scanned.pdf        image-only degraded scan, no text layer;
                                  full Udyam number visible (Bidder A's
                                  clean fully-verifiable case)
  sample_udyam_tech_solutions.pdf digital Udyam with a conflicting name (C)
  sample_financials.pdf           audited financial statement, turnover + FY (6.7)
  sample_oem_authorization.pdf    OEM authorization letter (6.7)
  sample_local_content.pdf        local content declaration (6.7)

Usage:
    python scripts/make_sample_docs.py [--out DIR]
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image, ImageDraw, ImageFilter, ImageFont

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

FONT_CANDIDATES = [
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
FONT_BOLD_CANDIDATES = [
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for path in (FONT_BOLD_CANDIDATES if bold else FONT_CANDIDATES):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _text_pdf(lines: list[tuple[int, str]], path: Path) -> None:
    """Digital PDF: real extractable text layer."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)  # A4
    y = 80.0
    for size, text in lines:
        page.insert_text((72, y), text, fontsize=size, fontname="helv")
        y += size + 18
    doc.save(path)
    doc.close()


def make_pan(path: Path) -> None:
    _text_pdf([
        (16, "INCOME TAX DEPARTMENT"),
        (13, "PERMANENT ACCOUNT NUMBER"),
        (13, ""),
        (13, "Name: ABC TECHNOLOGIES PVT LTD"),
        (13, "PAN : ABCDE1234F"),
        (13, "Date of Birth/Incorporation: 12/04/2011"),
        (11, "This is a computer-generated copy of the PAN record."),
        (11, "Issued under Section 139A of the Income Tax Act, 1961."),
    ], path)


def make_gst(path: Path) -> None:
    _text_pdf([
        (16, "GST CERTIFICATE OF REGISTRATION"),
        (13, "Government of India, Ministry of Finance"),
        (13, ""),
        (13, "GSTIN: 07ABCDE1234F1Z5"),
        (13, "Legal Name of Registered Person: ABC TECHNOLOGIES PVT LTD"),
        (13, "Trade Name: ABC Tech"),
        (13, "Date of Registration: 15/07/2019"),
        (13, "Status of Registration: Active"),
        (13, "State: Delhi (07)"),
        (11, "Principal place of business: New Delhi"),
    ], path)


def make_udyam_scanned(path: Path) -> None:
    """Image-only page (no text layer) at low effective DPI, visually degraded.

    Bidder A's clean case: the full registration number is visible, so OCR
    must recover it completely for UDYAM-001 to become verifiable.
    """
    width, height = 900, 1273          # ~110 DPI when scaled onto A4
    image = Image.new("RGB", (width, height), (247, 246, 241))
    draw = ImageDraw.Draw(image)

    draw.text((70, 60), "UDYAM REGISTRATION CERTIFICATE", font=_font(34, bold=True), fill=(20, 24, 40))
    draw.text((70, 112), "Ministry of Micro, Small and Medium Enterprises", font=_font(24), fill=(40, 44, 60))
    draw.text((70, 148), "Government of India", font=_font(24), fill=(40, 44, 60))
    draw.line((70, 200, width - 70, 200), fill=(120, 124, 140), width=2)

    rows = [
        (250, "Enterprise Name", "ABC TECHNOLOGIES PVT LTD"),
        (320, "Type of Enterprise", "Micro"),
        (390, "Date of Registration", "21/08/2021"),
        (460, "National Industrial Classification", "26200"),
        (530, "Entrepreneur Name", "RAJESH KUMAR SHARMA"),
    ]
    for y, label, value in rows:
        draw.text((70, y), f"{label}:", font=_font(24, bold=True), fill=(60, 64, 80))
        draw.text((430, y), value, font=_font(24), fill=(15, 18, 30))

    draw.text((70, 600), "Udyam Registration Number:", font=_font(24, bold=True), fill=(60, 64, 80))
    draw.text((430, 600), "UDYAM-DL-05-0004567", font=_font(24, bold=True), fill=(15, 18, 30))

    draw.line((70, height - 190, width - 70, height - 190), fill=(120, 124, 140), width=2)
    draw.text((70, height - 160), "This is a system-generated certificate.", font=_font(20), fill=(70, 74, 90))
    draw.text((70, height - 125), "Verification is subject to the Udyam registry.", font=_font(20), fill=(70, 74, 90))

    # Degradation: slight skew, blur, sensor noise, JPEG artifacts.
    image = image.rotate(0.7, resample=Image.BICUBIC, fillcolor=(247, 246, 241))
    image = image.filter(ImageFilter.GaussianBlur(radius=0.9))
    arr = np.asarray(image).astype(np.int16)
    rng = np.random.default_rng(42)
    noise = rng.integers(-28, 28, arr.shape, dtype=np.int16)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    image = Image.fromarray(arr)

    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=48)   # aggressive compression
    buf.seek(0)
    image = Image.open(buf).convert("RGB")

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(pymupdf.Rect(0, 0, 595, 842), stream=image_to_png_bytes(image))
    doc.save(path)
    doc.close()


def make_financials(path: Path) -> None:
    _text_pdf([
        (16, "AUDITED FINANCIAL STATEMENT"),
        (13, "For the Financial Year 2024-25"),
        (13, ""),
        (13, "Name of Entity: ABC TECHNOLOGIES PVT LTD"),
        (13, "Turnover (INR Crore): 12.40"),
        (13, "Financial Year: 2024-25"),
        (11, "Audited under the Companies Act, 2013."),
        (11, "This statement is submitted as part of the bid documents."),
    ], path)


def make_oem_authorization(path: Path) -> None:
    _text_pdf([
        (16, "OEM AUTHORIZATION LETTER"),
        (13, "Ref: OEM/AUTH/2026/0417"),
        (13, ""),
        (13, "To Whom It May Concern,"),
        (13, "M/s ABC TECHNOLOGIES PVT LTD is authorised to offer, supply and"),
        (13, "provide after-sales support for products of Siemens as our"),
        (13, "authorised channel partner for the territory of India."),
        (13, "This authorization is valid for the current financial year."),
        (13, "OEM: Siemens"),
        (11, "Authorised Signatory, Siemens"),
    ], path)


def make_local_content(path: Path) -> None:
    _text_pdf([
        (16, "LOCAL CONTENT DECLARATION"),
        (13, "Public Procurement (Preference to Make in India) Order, 2017"),
        (13, ""),
        (13, "Entity: ABC TECHNOLOGIES PVT LTD"),
        (13, "Item Category: Electrical Equipment"),
        (13, "Declared Local Content: 45%"),
        (11, "We declare that the declared local content percentage above is"),
        (11, "as per the DPIIT measurement methodology for this item category."),
    ], path)


def image_to_png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def make_udyam_text(path: Path, enterprise_name: str) -> None:
    """Digital Udyam certificate (real text layer) with a custom enterprise name."""
    _text_pdf([
        (16, "UDYAM REGISTRATION CERTIFICATE"),
        (13, "Ministry of Micro, Small and Medium Enterprises"),
        (13, "Government of India"),
        (13, ""),
        (13, f"Enterprise Name: {enterprise_name}"),
        (13, "Udyam Registration Number: UDYAM-DL-05-0004567"),
        (13, "Type of Enterprise: Micro"),
        (13, "Date of Registration: 21/08/2021"),
        (11, "System-generated certificate; verify against the Udyam registry."),
    ], path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Phase 3 sample documents")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    make_pan(out / "sample_pan.pdf")
    make_gst(out / "sample_gst.pdf")
    make_udyam_scanned(out / "sample_udyam_scanned.pdf")
    make_udyam_text(out / "sample_udyam_tech_solutions.pdf", "ABC Tech Solutions")
    make_financials(out / "sample_financials.pdf")
    make_oem_authorization(out / "sample_oem_authorization.pdf")
    make_local_content(out / "sample_local_content.pdf")

    for name in ("sample_pan.pdf", "sample_gst.pdf", "sample_udyam_scanned.pdf",
                 "sample_udyam_tech_solutions.pdf", "sample_financials.pdf",
                 "sample_oem_authorization.pdf", "sample_local_content.pdf"):
        p = out / name
        doc = pymupdf.open(p)
        chars = sum(len(page.get_text("text").strip()) for page in doc)
        kind = "text layer" if chars > 50 else "image only (OCR required)"
        print(f"{name:32} pages={doc.page_count}  extractable_chars={chars}  -> {kind}")
        doc.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
