"""
rebrand_pdf.py  –  Laurion Platform PDF Rebranding Tool
========================================================
Stamps every page of an exam PDF with your portal's branding:

  • Page 1  : branded Laurion cover (inserted before original content)
  • All pages: logo centred in footer

Performance fixes applied:
  - Logo loaded from disk once and cached (_LOGO_CACHE)
  - Cover overlay built once and cached (_COVER_CACHE)
  - Inner overlay built once and reused for all content pages (_INNER_CACHE)
  - ImageReader objects created once per call, not per page

Usage (standalone):
    python rebrand_pdf.py input.pdf output.pdf

Usage (Flask integration):
    from rebrand_pdf import rebrand_pdf_bytes
    branded = rebrand_pdf_bytes(open("exam.pdf","rb").read())
"""

import io
from pathlib import Path

from PIL import Image
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.utils import ImageReader

# ── Configuration ──────────────────────────────────────────────────────────────
PORTAL_NAME    = "Laurion"
PORTAL_TAGLINE = "Your Leading Exam Resource Portal"
PORTAL_URL     = "www.laurion.co.za"

SCRIPT_DIR = Path(__file__).parent
LOGO_PATH  = SCRIPT_DIR / "new_logo.png"

# Colours
NAVY          = (15/255,  37/255,  64/255)   # #0F2540
WHITE         = (1, 1, 1)
LIGHT_BLUE_BG = (0.878, 0.921, 0.961)

PAGE_W, PAGE_H = A4   # 595.28 × 841.89 pt
FOOTER_LOGO_H  = 28   # pt – logo height in footer

# ── Module-level caches ────────────────────────────────────────────────────────
_LOGO_CACHE:  Image.Image | None = None
_COVER_CACHE: bytes | None       = None
_INNER_CACHE: bytes | None       = None


# ── Helpers ────────────────────────────────────────────────────────────────────

def _logo_img() -> Image.Image:
    """Load logo from disk once; return a copy on every call."""
    global _LOGO_CACHE
    if _LOGO_CACHE is None:
        if LOGO_PATH.exists():
            _LOGO_CACHE = Image.open(LOGO_PATH).convert("RGBA")
        else:
            _LOGO_CACHE = Image.new("RGBA", (80, 80), (255, 255, 255, 255))
    return _LOGO_CACHE.copy()


def _logo_on_white_bg(logo: Image.Image, pad: int = 3) -> Image.Image:
    """Paste logo onto white background (keeps it visible on dark bars)."""
    w, h = logo.size
    bg = Image.new("RGB", (w + pad * 2, h + pad * 2), (255, 255, 255))
    if logo.mode == "RGBA":
        bg.paste(logo, (pad, pad), logo)
    else:
        bg.paste(logo, (pad, pad))
    return bg


def _overlay_to_pdf_page(buf: io.BytesIO):
    """Return first page of a reportlab-generated PDF buffer."""
    return PdfReader(buf).pages[0]


# ── Cover page ─────────────────────────────────────────────────────────────────

def _build_cover_bytes() -> bytes:
    buf = io.BytesIO()
    c   = rl_canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    logo   = _logo_img()
    aspect = logo.width / logo.height
    ir     = ImageReader(logo)

    logo_wb   = _logo_on_white_bg(logo, pad=3)
    ir_wb     = ImageReader(logo_wb)
    wb_aspect = logo_wb.width / logo_wb.height

    # ── Top header bar ────────────────────────────────────────────────────
    c.setFillColorRGB(*NAVY)
    c.rect(0, h - 48, w, 48, fill=1, stroke=0)

    logo_h_pt = 34
    wb_logo_w = logo_h_pt * wb_aspect
    c.drawImage(ir_wb, 6, h - 45, width=wb_logo_w, height=logo_h_pt,
                mask="auto", preserveAspectRatio=True)

    c.setFillColorRGB(*WHITE)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(6 + wb_logo_w + 6, h - 20, PORTAL_NAME)
    c.setFont("Helvetica", 8)
    c.drawString(6 + wb_logo_w + 6, h - 32, PORTAL_TAGLINE)

    c.drawImage(ir_wb, w - wb_logo_w - 6, h - 45, width=wb_logo_w,
                height=logo_h_pt, mask="auto", preserveAspectRatio=True)

    # ── White body ────────────────────────────────────────────────────────
    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, w, h - 48, fill=1, stroke=0)

    # ── Large centre logo ─────────────────────────────────────────────────
    big_h = 180
    big_w = big_h * aspect
    c.drawImage(ir, (w - big_w) / 2, h - 48 - 80 - big_h,
                width=big_w, height=big_h, mask="auto", preserveAspectRatio=True)

    # ── Headline text ─────────────────────────────────────────────────────
    text_y = h - 48 - 80 - big_h - 50
    c.setFillColorRGB(0.05, 0.22, 0.45)
    c.setFont("Helvetica-BoldOblique", 22)
    c.drawCentredString(w / 2, text_y,      "You have Downloaded, yet Another Great")
    c.drawCentredString(w / 2, text_y - 30, "Resource to assist you with your Studies \u25A0")

    c.setFont("Helvetica-BoldOblique", 16)
    c.drawCentredString(w / 2, text_y - 75, "Thank You for Supporting Us")

    c.setFont("Helvetica-Bold", 12)
    c.setFillColorRGB(0, 0, 0)
    c.drawCentredString(w / 2, text_y - 110, "Your Leading Past Year Exam Paper Resource Portal")

    c.setFillColorRGB(0.13, 0.46, 0.71)
    c.setFont("Helvetica", 11)
    c.drawCentredString(w / 2, text_y - 130, f"Visit us @ {PORTAL_URL}")

    # ── Bottom branded box ────────────────────────────────────────────────
    box_h, box_y = 120, 20
    c.setFillColorRGB(*LIGHT_BLUE_BG)
    c.rect(30, box_y, w - 60, box_h, fill=1, stroke=0)

    small_h = 80
    small_w = small_h * aspect
    c.drawImage(ir, (w - small_w) / 2, box_y + (box_h - small_h) / 2,
                width=small_w, height=small_h, mask="auto", preserveAspectRatio=True)

    c.save()
    buf.seek(0)
    return buf.read()


def _get_cover_overlay() -> io.BytesIO:
    """Return cached cover overlay as a fresh BytesIO each call."""
    global _COVER_CACHE
    if _COVER_CACHE is None:
        _COVER_CACHE = _build_cover_bytes()
    return io.BytesIO(_COVER_CACHE)


# ── Footer-only overlay (used on every page of original content) ───────────────

def _build_inner_bytes() -> bytes:
    """
    Single-page overlay: just the Laurion logo centred in the footer.
    No header bar — keeps original exam content fully visible.
    """
    buf = io.BytesIO()
    c   = rl_canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    logo   = _logo_img()
    aspect = logo.width / logo.height
    ir     = ImageReader(logo)

    foot_h = FOOTER_LOGO_H
    foot_w = foot_h * aspect
    x = (w - foot_w) / 2   # horizontally centred
    y = 6                   # 6 pt from bottom edge

    c.drawImage(ir, x, y, width=foot_w, height=foot_h,
                mask="auto", preserveAspectRatio=True)

    c.save()
    buf.seek(0)
    return buf.read()


def _get_inner_overlay() -> io.BytesIO:
    """Return cached inner overlay as a fresh BytesIO each call."""
    global _INNER_CACHE
    if _INNER_CACHE is None:
        _INNER_CACHE = _build_inner_bytes()
    return io.BytesIO(_INNER_CACHE)


# ── Main rebranding function ───────────────────────────────────────────────────

def rebrand_pdf_bytes(pdf_bytes: bytes) -> bytes:
    """
    Accept raw PDF bytes, return rebranded PDF bytes.

    Output structure:
      [0]        Branded Laurion cover page
      [1 … N]    Original pages, each with logo centred in footer
    """
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()

    # Build overlays once (cached after first call)
    cover_page = _overlay_to_pdf_page(_get_cover_overlay())
    inner_page = _overlay_to_pdf_page(_get_inner_overlay())

    # Insert branded cover
    writer.add_page(cover_page)

    # Stamp every original page with footer logo
    for page in reader.pages:
        page.merge_page(inner_page)
        writer.add_page(page)

    out_buf = io.BytesIO()
    writer.write(out_buf)
    return out_buf.getvalue()


# ── File helper & CLI ──────────────────────────────────────────────────────────

def rebrand_pdf_file(input_path: str, output_path: str) -> None:
    """Rebrand a PDF file on disk."""
    with open(input_path, "rb") as f:
        data = f.read()
    branded = rebrand_pdf_bytes(data)
    with open(output_path, "wb") as f:
        f.write(branded)
    print(f"✅  Branded PDF saved → {output_path}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python rebrand_pdf.py input.pdf output.pdf")
        sys.exit(1)
    rebrand_pdf_file(sys.argv[1], sys.argv[2])
