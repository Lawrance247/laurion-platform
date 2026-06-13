"""
fix_subjects.py  —  Fix wrongly-assigned subjects in Laurion DB
================================================================
Run this ONCE to correct all materials that were uploaded with
the wrong subject code (e.g. eng_hl instead of acc, geo, etc.)

RUN:
    python fix_subjects.py --check      # show what's wrong
    python fix_subjects.py --fix        # actually fix it
"""

import re
import sys
import argparse
from urllib.parse import urlparse
import psycopg2

# ── CONFIG ─────────────────────────────────────────────────────────────────────

DATABASE_URL = "postgresql://postgres.wjcbshnvjwcsevbvefjv:Lawrancelaurion@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"

# ── SUBJECT MAP (longest/most specific first) ──────────────────────────────────

SUBJECT_MAP = [
    ("mathematical_literacy",           "mlit"),
    ("mathematical literacy",           "mlit"),
    ("maths_lit",                       "mlit"),
    ("math_lit",                        "mlit"),
    ("technical_mathematics",           "tech_math"),
    ("technical mathematics",           "tech_math"),
    ("technical_sciences",              "tech_sci"),
    ("technical sciences",              "tech_sci"),
    ("physical_sciences",               "phy"),
    ("physical sciences",               "phy"),
    ("physical_science",                "phy"),
    ("life_sciences",                   "ls"),
    ("life sciences",                   "ls"),
    ("life_science",                    "ls"),
    ("life_orientation",                "lo"),
    ("life orientation",                "lo"),
    ("agricultural_sciences",           "agri"),
    ("agricultural sciences",           "agri"),
    ("agricultural_technology",         "agri_tech"),
    ("agricultural technology",         "agri_tech"),
    ("agricultural_science",            "agri"),
    ("computer_application_technology", "cat"),
    ("computer application technology", "cat"),
    ("computer_applications",           "cat"),
    ("information_technology",          "it"),
    ("information technology",          "it"),
    ("electrical_technology",           "egs"),
    ("electrical technology",           "egs"),
    ("mechanical_technology",           "mech"),
    ("mechanical technology",           "mech"),
    ("civil_technology",                "civil"),
    ("civil technology",                "civil"),
    ("hospitality_studies",             "hosp"),
    ("hospitality studies",             "hosp"),
    ("business_studies",                "bs"),
    ("business studies",                "bs"),
    ("consumer_studies",                "cons"),
    ("consumer studies",                "cons"),
    ("religion_studies",                "rel"),
    ("religion studies",                "rel"),
    ("visual_arts",                     "vis_art"),
    ("visual arts",                     "vis_art"),
    ("dramatic_arts",                   "drama"),
    ("dramatic arts",                   "drama"),
    ("dance_studies",                   "dance"),
    ("dance studies",                   "dance"),
    ("mathematics",                     "math"),
    ("accounting",                      "acc"),
    ("economics",                       "econ"),
    ("geography",                       "geo"),
    ("history",                         "hist"),
    ("tourism",                         "tour"),
    ("music",                           "music"),
    # Languages — specific variants first
    ("english_fal",                     "eng_fal"),
    ("english fal",                     "eng_fal"),
    ("english_hl",                      "eng_hl"),
    ("english hl",                      "eng_hl"),
    ("afrikaans_fal",                   "afr_fal"),
    ("afrikaans fal",                   "afr_fal"),
    ("afrikaans_hl",                    "afr_hl"),
    ("afrikaans hl",                    "afr_hl"),
    ("isizulu_fal",                     "zul_fal"),
    ("isizulu fal",                     "zul_fal"),
    ("isizulu_hl",                      "zul_hl"),
    ("isizulu hl",                      "zul_hl"),
    ("isizulu",                         "zul_fal"),
    ("isixhosa_fal",                    "xho_fal"),
    ("isixhosa fal",                    "xho_fal"),
    ("isixhosa_hl",                     "xho_hl"),
    ("isixhosa hl",                     "xho_hl"),
    ("isixhosa",                        "xho_fal"),
    ("sepedi",                          "sep_fal"),
    ("sesotho",                         "sot_fal"),
    ("setswana",                        "sot_fal"),
    ("afrikaans",                       "afr_fal"),
    # Do NOT include plain "english" — it appears as a language tag in every filename
]

# Noise words to strip from the END of a title before matching subject
NOISE = {
    "memo", "english", "afrikaans", "and", "answerbook", "answer", "book",
    "addendum", "annexure", "paper", "p1", "p2", "p3", "p4",
    "1", "2", "3", "4", "5",
    "eastern", "cape", "western", "northern", "north", "west",
    "gauteng", "kwazulu", "natal", "limpopo", "mpumalanga", "free", "state",
    "november", "may", "june", "nov",
    "sal", "hl", "fal",   # keep these in noise so they don't block earlier matches
}


def guess_subject_from_title(title: str) -> str | None:
    """Detect subject from a human-readable title like '2024 November Accounting Paper 1 English'"""
    # Work with lowercase
    lower = title.lower()

    # Try multi-word matches first (most specific)
    for keyword, code in SUBJECT_MAP:
        if keyword in lower:
            return code

    # Fallback: strip noise words from the right and try again
    words = re.sub(r"[^a-z0-9 ]", " ", lower).split()
    # Remove leading year
    if words and re.match(r"^\d{4}$", words[0]):
        words = words[1:]
    # Strip noise from right
    while words and words[-1] in NOISE:
        words.pop()
    cleaned = " ".join(words)

    for keyword, code in SUBJECT_MAP:
        if keyword in cleaned:
            return code

    return None


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Show current subject breakdown and mismatches")
    parser.add_argument("--fix",   action="store_true", help="Re-assign subjects based on title")
    args = parser.parse_args()

    if not args.check and not args.fix:
        parser.print_help()
        sys.exit(1)

    conn = db_connect()
    cur  = conn.cursor()
    print("✅ Connected to database\n")

    if args.check:
        cur.execute("SELECT subject, COUNT(*) FROM material GROUP BY subject ORDER BY COUNT(*) DESC")
        rows = cur.fetchall()
        print("Current subject breakdown:")
        for subject, count in rows:
            print(f"  {subject:20s}: {count}")
        print(f"\n  Total: {sum(r[1] for r in rows)}")

        # Show sample of likely wrong ones
        cur.execute("SELECT id, title, subject FROM material WHERE subject='eng_hl' LIMIT 10")
        samples = cur.fetchall()
        if samples:
            print(f"\nSample eng_hl entries (likely wrong):")
            for id_, title, subj in samples:
                guessed = guess_subject_from_title(title)
                print(f"  [{id_}] '{title}' → should be: {guessed}")

    if args.fix:
        cur.execute("SELECT id, title, subject FROM material")
        rows = cur.fetchall()
        fixed = 0
        unchanged = 0
        unknown = 0

        for id_, title, current_subject in rows:
            guessed = guess_subject_from_title(title)
            if guessed is None:
                print(f"  ⚠️  Can't detect: '{title}' (keeping {current_subject})")
                unknown += 1
            elif guessed != current_subject:
                cur.execute("UPDATE material SET subject=%s WHERE id=%s", (guessed, id_))
                print(f"  ✅ [{id_}] '{title[:50]}' → {current_subject} → {guessed}")
                fixed += 1
            else:
                unchanged += 1

        conn.commit()
        print(f"\n{'='*60}")
        print(f"Fixed:     {fixed}")
        print(f"Unchanged: {unchanged}")
        print(f"Unknown:   {unknown}")
        print(f"{'='*60}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
