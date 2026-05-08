"""
rebrand_pdf.py  –  Laurion Platform PDF Rebranding Tool
========================================================
Stamps every page of an exam PDF with your portal's branding:

  • Page 1  : replaces the SA Exam Papers cover with a Laurion-branded cover
  • Page 2+ : adds a branded header bar + footer logo on every content page

Usage (standalone):
    python rebrand_pdf.py input.pdf output.pdf

Usage (Flask integration):
    from rebrand_pdf import rebrand_pdf_bytes
    branded = rebrand_pdf_bytes(open("exam.pdf","rb").read())
    # return branded as Flask response
"""

import io
import os
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.utils import ImageReader
import reportlab.lib.colors as colors

# ── Configuration ─────────────────────────────────────────────────────────────
PORTAL_NAME   = "Laurion"
PORTAL_TAGLINE = "Your Leading Exam Resource Portal"
PORTAL_URL    = "www.laurion.co.za"
HEADER_TEXT   = "This past paper was brought to you by Your Leading Exam Resource"

# Paths – adjust if needed
SCRIPT_DIR  = Path(__file__).parent
LOGO_PATH   = SCRIPT_DIR / "new_logo.png"

# Branding colours  (dark navy header like the preview)
NAVY   = (15/255, 37/255, 64/255)          # #0F2540
GOLD   = (212/255, 160/255, 23/255)        # #D4A017  (accent)
WHITE  = (1, 1, 1)
LIGHT_BLUE_BG = (0.878, 0.921, 0.961)      # cover light-blue box

PAGE_W, PAGE_H = A4   # 595.28 x 841.89 pt
HEADER_H = 36         # pt – height of the header bar on inner pages
FOOTER_H = 32         # pt – height of footer on inner pages

# ── Helpers ───────────────────────────────────────────────────────────────────

def _logo_img() -> Image.Image:
    """Return the logo as a PIL image (white background, no processing needed)."""
    if LOGO_PATH.exists():
        return Image.open(LOGO_PATH).convert("RGB")
    return Image.new("RGB", (80, 80), (255, 255, 255))


def _logo_on_white_bg(logo: Image.Image, pad: int = 4) -> Image.Image:
    """
    Paste the logo onto a white background so it stays visible on dark surfaces.
    Works with both RGB and RGBA logos.
    """
    w, h = logo.size
    bg = Image.new("RGB", (w + pad * 2, h + pad * 2), (255, 255, 255))
    if logo.mode == "RGBA":
        bg.paste(logo, (pad, pad), logo)
    else:
        bg.paste(logo, (pad, pad))
    return bg


def _overlay_to_pdf_page(overlay_buf: io.BytesIO) -> object:
    """Read a reportlab-generated PDF bytes buffer and return its first page."""
    return PdfReader(overlay_buf).pages[0]


# ── Cover page overlay ────────────────────────────────────────────────────────

def _make_cover_overlay() -> io.BytesIO:
    """
    Build a one-page PDF overlay that replicates the branded cover shown
    in rebranding_preview.pdf page 1.
    """
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    # ── Top header bar ──────────────────────────────────────────────────
    c.setFillColorRGB(*NAVY)
    c.rect(0, h - 48, w, 48, fill=1, stroke=0)

    # Logo in header (left side, small)
    logo = _logo_img()
    logo_h_pt = 34
    aspect = logo.width / logo.height
    logo_w_pt = logo_h_pt * aspect
    # White-bg logo for dark navy header; raw logo for white body areas
    logo_wb = _logo_on_white_bg(logo, pad=3)
    wb_aspect = logo_wb.width / logo_wb.height
    ir_wb = ImageReader(logo_wb)
    ir     = ImageReader(logo)

    # Header logos (on dark navy — use white-bg version)
    wb_logo_w = logo_h_pt * wb_aspect
    c.drawImage(ir_wb, 6, h - 45, width=wb_logo_w, height=logo_h_pt,
                mask="auto", preserveAspectRatio=True)

    # Portal name & tagline in header
    c.setFillColorRGB(*WHITE)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(6 + wb_logo_w + 6, h - 20, PORTAL_NAME)
    c.setFont("Helvetica", 8)
    c.drawString(6 + wb_logo_w + 6, h - 32, PORTAL_TAGLINE)

    # Logo in header right side
    c.drawImage(ir_wb, w - wb_logo_w - 6, h - 45, width=wb_logo_w,
                height=logo_h_pt, mask="auto", preserveAspectRatio=True)

    # ── White body covering old SA Exam Papers branding ─────────────────
    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, w, h - 48, fill=1, stroke=0)

    # ── Centre logo (large) — on white body, use clean transparent logo ─
    big_h = 180
    big_w = big_h * aspect
    c.drawImage(ir, (w - big_w) / 2, h - 48 - 80 - big_h,
                width=big_w, height=big_h, mask="auto", preserveAspectRatio=True)

    # ── Main headline ───────────────────────────────────────────────────
    c.setFillColorRGB(0.05, 0.22, 0.45)
    c.setFont("Helvetica-BoldOblique", 22)
    line1 = "You have Downloaded, yet Another Great"
    line2 = "Resource to assist you with your Studies \u25A0"
    text_y = h - 48 - 80 - big_h - 50
    c.drawCentredString(w / 2, text_y, line1)
    c.drawCentredString(w / 2, text_y - 30, line2)

    # ── Sub-headline ────────────────────────────────────────────────────
    c.setFont("Helvetica-BoldOblique", 16)
    c.drawCentredString(w / 2, text_y - 75, "Thank You for Supporting Us")

    # ── Portal name (bold) ──────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 12)
    c.setFillColorRGB(0, 0, 0)
    c.drawCentredString(w / 2, text_y - 110, f"Your Leading Past Year Exam Paper Resource Portal")

    # ── URL ─────────────────────────────────────────────────────────────
    c.setFillColorRGB(0.13, 0.46, 0.71)
    c.setFont("Helvetica", 11)
    c.drawCentredString(w / 2, text_y - 130, f"Visit us @ {PORTAL_URL}")

    # ── Bottom branded box ───────────────────────────────────────────────
    box_h = 120
    box_y = 20
    c.setFillColorRGB(*LIGHT_BLUE_BG)
    c.rect(30, box_y, w - 60, box_h, fill=1, stroke=0)

    # Small logo inside box
    small_h = 80
    small_w = small_h * aspect
    c.drawImage(ImageReader(logo), (w - small_w) / 2, box_y + (box_h - small_h) / 2,
                width=small_w, height=small_h, mask="auto",
                preserveAspectRatio=True)

    c.save()
    buf.seek(0)
    return buf


# ── Inner page overlay (header + footer) ─────────────────────────────────────

def _make_inner_overlay(page_num: int, total_pages: int) -> io.BytesIO:
    """
    Build a one-page PDF overlay for content pages (page 2 onward).
    Adds:  branded header bar at top  +  small logo at bottom footer.
    """
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    logo = _logo_img()
    aspect = logo.width / logo.height

    # ── Header bar ──────────────────────────────────────────────────────
    c.setFillColorRGB(*NAVY)
    c.rect(0, h - HEADER_H, w, HEADER_H, fill=1, stroke=0)

    logo_h_pt = HEADER_H - 4
    logo_w_pt = logo_h_pt * aspect
    logo_wb = _logo_on_white_bg(logo, pad=2)
    wb_aspect = logo_wb.width / logo_wb.height
    ir_wb  = ImageReader(logo_wb)
    ir     = ImageReader(logo)

    wb_logo_w = logo_h_pt * wb_aspect
    # Left logo (on navy — white bg version)
    c.drawImage(ir_wb, 3, h - HEADER_H + 2, width=wb_logo_w,
                height=logo_h_pt, mask="auto", preserveAspectRatio=True)

    # Header text
    c.setFillColorRGB(*WHITE)
    c.setFont("Helvetica-Bold", 8)
    label = f"{PORTAL_NAME} | {HEADER_TEXT}"
    c.drawString(wb_logo_w + 8, h - HEADER_H + 13, label)

    # Right logo (on navy — white bg version)
    c.drawImage(ir_wb, w - wb_logo_w - 3, h - HEADER_H + 2,
                width=wb_logo_w, height=logo_h_pt, mask="auto",
                preserveAspectRatio=True)

    # ── Footer logo (on white page — clean transparent version) ──────────
    foot_h = 24
    foot_w = foot_h * aspect
    c.drawImage(ir, (w - foot_w) / 2, 4, width=foot_w, height=foot_h,
                mask="auto", preserveAspectRatio=True)

    c.save()
    buf.seek(0)
    return buf


# ── Main rebranding function ──────────────────────────────────────────────────

def rebrand_pdf_bytes(pdf_bytes: bytes) -> bytes:
    """
    Accept raw PDF bytes, return rebranded PDF bytes.
    Inserts a branded cover as page 1 and leaves all original pages untouched.
    """
    reader  = PdfReader(io.BytesIO(pdf_bytes))
    writer  = PdfWriter()

    # ── Page 1: our branded cover (new, inserted before original content) ──
    cover_page = _overlay_to_pdf_page(_make_cover_overlay())
    writer.add_page(cover_page)

    # ── Remaining pages: original content, completely untouched ────────────
    for page in reader.pages:
        writer.add_page(page)

    out_buf = io.BytesIO()
    writer.write(out_buf)
    return out_buf.getvalue()


def rebrand_pdf_file(input_path: str, output_path: str) -> None:
    """Rebrand a PDF file on disk."""
    with open(input_path, "rb") as f:
        data = f.read()
    branded = rebrand_pdf_bytes(data)
    with open(output_path, "wb") as f:
        f.write(branded)
    print(f"✅  Branded PDF saved → {output_path}")


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python rebrand_pdf.py input.pdf output.pdf")
        sys.exit(1)
    rebrand_pdf_file(sys.argv[1], sys.argv[2])
