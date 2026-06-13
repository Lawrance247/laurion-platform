"""
scrape_nsc_papers.py  —  Laurion NSC Bulk Importer
===================================================
Uploads NSC past papers to Cloudinary + Supabase.

TWO MODES:
  1. FOLDER MODE  — point it at a folder of PDFs you've downloaded
  2. URL MODE     — give it a text file of direct PDF URLs

SETUP:
    pip install requests cloudinary psycopg2-binary

CONFIGURE:
    Fill in your credentials in the CONFIG section below.

USAGE:
    # Upload all PDFs in a folder:
    python scrape_nsc_papers.py --folder "C:/Users/lawra/Downloads/papers"

    # Upload from a list of URLs (one URL per line in urls.txt):
    python scrape_nsc_papers.py --urls urls.txt

    # Dry run first (no uploads):
    python scrape_nsc_papers.py --folder "C:/Users/lawra/Downloads/papers" --dry-run
"""

import os
import re
import sys
import time
import argparse
from pathlib import Path
from urllib.parse import urlparse

import requests
import cloudinary
import cloudinary.uploader
import psycopg2

# ── CONFIG ─────────────────────────────────────────────────────────────────────

CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "dfxhf8ldx")
CLOUDINARY_API_KEY    = os.getenv("CLOUDINARY_API_KEY",    "495571835286512")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "6QTGOXtNU1itbF4RaKVTfL-eq7M")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres.wjcbshnvjwcsevbvefjv:Lawrancelaurion@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"
)

UPLOADED_BY    = "LawranceFounder"
DOWNLOAD_DELAY = 1.0   # seconds between URL downloads

# ── SUBJECT MAP ────────────────────────────────────────────────────────────────
# Maps keywords in filename → subject code in your server.py SUBJECTS dict

SUBJECT_MAP = [
    # Order matters — check longer/more specific strings first
    ("mathematical_literacy",       "mlit"),
    ("maths_lit",                   "mlit"),
    ("math_lit",                    "mlit"),
    ("technical_mathematics",       "tech_math"),
    ("technical_sciences",          "tech_sci"),
    ("physical_sciences",           "phy"),
    ("physical_science",            "phy"),
    ("life_sciences",               "ls"),
    ("life_science",                "ls"),
    ("mathematics",                 "math"),
    ("english_fal",                 "eng_fal"),
    ("english_hl",                  "eng_hl"),
    ("english",                     "eng_hl"),
    ("afrikaans_fal",               "afr_fal"),
    ("afrikaans_hl",                "afr_hl"),
    ("afrikaans",                   "afr_fal"),
    ("isizulu_fal",                 "zul_fal"),
    ("isizulu_hl",                  "zul_hl"),
    ("isizulu",                     "zul_fal"),
    ("isixhosa_fal",                "xho_fal"),
    ("isixhosa_hl",                 "xho_hl"),
    ("isixhosa",                    "xho_fal"),
    ("sepedi",                      "sep_fal"),
    ("sesotho",                     "sot_fal"),
    ("setswana",                    "sot_fal"),
    ("geography",                   "geo"),
    ("history",                     "hist"),
    ("religion_studies",            "rel"),
    ("accounting",                  "acc"),
    ("business_studies",            "bs"),
    ("economics",                   "econ"),
    ("computer_applications",       "cat"),
    ("information_technology",      "it"),
    ("visual_arts",                 "vis_art"),
    ("dramatic_arts",               "drama"),
    ("music",                       "music"),
    ("dance_studies",               "dance"),
    ("life_orientation",            "lo"),
    ("electrical_technology",       "egs"),
    ("mechanical_technology",       "mech"),
    ("civil_technology",            "civil"),
    ("hospitality_studies",         "hosp"),
    ("tourism",                     "tour"),
    ("agricultural_sciences",       "agri"),
    ("agricultural_technology",     "agri_tech"),
    ("consumer_studies",            "cons"),
]

GRADE_PATTERN = re.compile(r"gr(?:ade)?[-_\s]?(\d{1,2})", re.IGNORECASE)

# ── HELPERS ────────────────────────────────────────────────────────────────────

def normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def guess_subject(filename: str) -> str | None:
    name = normalise(filename)
    for keyword, code in SUBJECT_MAP:
        if keyword in name:
            return code
    return None


def guess_grade(filename: str) -> int:
    m = GRADE_PATTERN.search(filename)
    if m:
        g = int(m.group(1))
        if 8 <= g <= 12:
            return g
    return 12   # default to Grade 12 for NSC papers


def clean_title(filename: str) -> str:
    name = Path(filename).stem
    name = re.sub(r"[_\-]+", " ", name).strip()
    name = re.sub(r"\s*\d{7,}\s*$", "", name).strip()  # remove timestamps
    return " ".join(w.capitalize() for w in name.split())


def db_connect():
    url = DATABASE_URL
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    p = urlparse(url.split("?")[0])
    return psycopg2.connect(
        host=p.hostname, port=p.port or 5432,
        dbname=p.path.lstrip("/"),
        user=p.username, password=p.password,
        sslmode="require",
    )


def already_exists(cur, title, subject, grade):
    cur.execute(
        "SELECT id FROM material WHERE title=%s AND subject=%s AND grade=%s",
        (title, subject, grade)
    )
    return cur.fetchone() is not None


def upload_cloudinary(data: bytes, filename: str) -> str:
    public_id = f"laurion/nsc/{Path(filename).stem}_{int(time.time())}"
    result = cloudinary.uploader.upload(
        data, resource_type="raw",
        public_id=public_id,
        use_filename=True, unique_filename=False,
    )
    return result["secure_url"]


def save_to_db(cur, conn, title, url, subject, grade):
    cur.execute(
        "INSERT INTO material (title, filename, subject, grade, uploaded_by, downloads) "
        "VALUES (%s, %s, %s, %s, %s, 0)",
        (title, url, subject, grade, UPLOADED_BY)
    )
    conn.commit()


def process_item(name: str, get_bytes, cur, conn, dry_run: bool, counters: dict):
    title   = clean_title(name)
    subject = guess_subject(name)
    grade   = guess_grade(name)

    if not subject:
        print(f"  ⏭️  SKIP (can't detect subject): {name}")
        counters["skipped"] += 1
        return

    print(f"\n  📄 {title}")
    print(f"     Subject: {subject} | Grade: {grade}")

    if dry_run:
        print(f"     ✅ Would upload")
        counters["uploaded"] += 1
        return

    if already_exists(cur, title, subject, grade):
        print(f"     ⏭️  Already in DB")
        counters["skipped"] += 1
        return

    try:
        data = get_bytes()
        print(f"     ⬇️  Got {len(data)//1024}KB")
    except Exception as e:
        print(f"     ❌ Read/download failed: {e}")
        counters["failed"] += 1
        return

    try:
        cloud_url = upload_cloudinary(data, name)
        print(f"     ☁️  Uploaded to Cloudinary")
    except Exception as e:
        print(f"     ❌ Cloudinary error: {e}")
        counters["failed"] += 1
        return

    try:
        save_to_db(cur, conn, title, cloud_url, subject, grade)
        print(f"     💾 Saved to DB")
        counters["uploaded"] += 1
    except Exception as e:
        print(f"     ❌ DB error: {e}")
        conn.rollback()
        counters["failed"] += 1


# ── MAIN ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Laurion NSC Bulk Importer")
    parser.add_argument("--folder", help="Path to folder of PDF files")
    parser.add_argument("--urls",   help="Path to text file with one PDF URL per line")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.folder and not args.urls:
        parser.print_help()
        print("\n❌ Please provide --folder or --urls")
        sys.exit(1)

    dry_run = args.dry_run
    if dry_run:
        print("🔍 DRY RUN — nothing will be uploaded\n")
        cur = conn = None
    else:
        cloudinary.config(
            cloud_name=CLOUDINARY_CLOUD_NAME,
            api_key=CLOUDINARY_API_KEY,
            api_secret=CLOUDINARY_API_SECRET,
        )
        conn = db_connect()
        cur  = conn.cursor()
        print("✅ Connected to Cloudinary + Database\n")

    counters = {"uploaded": 0, "skipped": 0, "failed": 0}

    # ── FOLDER MODE ────────────────────────────────────────────────────────────
    if args.folder:
        folder = Path(args.folder)
        pdfs   = sorted(folder.glob("**/*.pdf")) + sorted(folder.glob("**/*.PDF"))
        print(f"📁 Found {len(pdfs)} PDFs in {folder}\n{'='*60}")

        for pdf_path in pdfs:
            process_item(
                name      = pdf_path.name,
                get_bytes = lambda p=pdf_path: p.read_bytes(),
                cur=cur, conn=conn, dry_run=dry_run, counters=counters
            )

    # ── URL MODE ───────────────────────────────────────────────────────────────
    if args.urls:
        with open(args.urls) as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]

        print(f"🔗 Found {len(urls)} URLs\n{'='*60}")
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

        for url in urls:
            name = url.split("/")[-1].split("?")[0]
            if not name.lower().endswith(".pdf"):
                name += ".pdf"

            def fetch(u=url):
                r = requests.get(u, headers=headers, timeout=30)
                r.raise_for_status()
                return r.content

            process_item(
                name=name, get_bytes=fetch,
                cur=cur, conn=conn, dry_run=dry_run, counters=counters
            )
            if not dry_run:
                time.sleep(DOWNLOAD_DELAY)

    # ── SUMMARY ────────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"✅ Done!  Uploaded: {counters['uploaded']}  |  Skipped: {counters['skipped']}  |  Failed: {counters['failed']}")
    print(f"{'='*60}")

    if not dry_run and conn:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
