from flask import Flask, render_template, request, redirect, session, url_for, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from datetime import datetime
from sqlalchemy import func
import os
import io
import cloudinary
import cloudinary.uploader
from flask import send_file
from rebrand_pdf import rebrand_pdf_bytes

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "00538db5f43fef83c1b7c6c04440766e4930f2dfb305f9011d1e7993ce416dd2")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////tmp/laurion.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
if "postgresql" in DATABASE_URL and "sslmode" not in DATABASE_URL:
    DATABASE_URL += "?sslmode=require"

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# Cloudinary config (set these in Render environment variables)
cloudinary.config(
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key    = os.getenv("CLOUDINARY_API_KEY"),
    api_secret = os.getenv("CLOUDINARY_API_SECRET"),
)

# ── ADMIN CONFIG ─────────────────────────────────────────────────────────────
ADMIN_USERNAME = "LawranceFounder"

# ── CAPS SUBJECTS BY PHASE ────────────────────────────────────────────────
# Senior Phase: Grades 8–9 (compulsory + common electives)
SUBJECTS_GR89 = {
    "eng":   "English Home Language",
    "afr":   "Afrikaans First Additional Language",
    "math":  "Mathematics",
    "ns":    "Natural Sciences",
    "ss":    "Social Sciences",
    "ems":   "Economic Management Sciences",
    "tech":  "Technology",
    "lo":    "Life Orientation",
    "ca":    "Creative Arts",
    "isizulu": "IsiZulu",
    "isixhosa":"IsiXhosa",
    "sesotho": "Sesotho",
    "setswana":"Setswana",
}

# FET Phase: Grades 10–12
SUBJECTS_FET = {
    # Languages (compulsory)
    "eng":   "English Home Language",
    "afr":   "Afrikaans First Additional Language",
    "isizulu": "IsiZulu",
    "isixhosa":"IsiXhosa",
    "sesotho": "Sesotho",
    "setswana":"Setswana",
    "sepedi":  "Sepedi",
    "xitsonga":"Xitsonga",
    "tshivenda":"Tshivenda",
    "siswati": "Siswati",
    "isindebele":"IsiNdebele",
    # Compulsory
    "lo":    "Life Orientation",
    # Mathematics stream
    "math":  "Mathematics",
    "mlit":  "Mathematical Literacy",
    "techmath":"Technical Mathematics",
    # Sciences
    "phy":   "Physical Sciences",
    "techsci":"Technical Sciences",
    "ls":    "Life Sciences",
    "agri":  "Agricultural Sciences",
    "ms":    "Marine Sciences",
    # Commerce
    "acc":   "Accounting",
    "bs":    "Business Studies",
    "econ":  "Economics",
    # Humanities
    "geo":   "Geography",
    "hist":  "History",
    "reli":  "Religion Studies",
    # Technology
    "it":    "Information Technology",
    "cat":   "Computer Applications Technology",
    "egd":   "Engineering Graphics & Design",
    "mechtech":"Mechanical Technology",
    "elecserv":"Electrical Technology",
    "civiltech":"Civil Technology",
    "agritech":"Agricultural Technology",
    # Arts
    "drama": "Dramatic Arts",
    "music": "Music",
    "visart":"Visual Arts",
    "design":"Design",
    # Consumer
    "cons":  "Consumer Studies",
    "hosp":  "Hospitality Studies",
    "tour":  "Tourism",
    # Sport & Physical
    "sportsc":"Sport & Exercise Science",
}

# Combined for general use — FET takes priority, GR89-only subjects appended
SUBJECTS = {**SUBJECTS_FET, **SUBJECTS_GR89}
# Simple merge: FET already has all subjects, GR89 adds the phase-specific ones
# Just use a plain merged dict with no broken dedup logic
SUBJECTS = dict(SUBJECTS_GR89)
SUBJECTS.update(SUBJECTS_FET)

SUBJECT_ICONS = {
    "eng":"🇬🇧", "afr":"🇿🇦", "isizulu":"🗣️", "isixhosa":"🗣️",
    "sesotho":"🗣️","setswana":"🗣️","sepedi":"🗣️","xitsonga":"🗣️",
    "tshivenda":"🗣️","siswati":"🗣️","isindebele":"🗣️",
    "math":"📊","mlit":"📐","techmath":"🔢",
    "phy":"⚛️","techsci":"🔬","ls":"🌿","agri":"🌾","ms":"🐟",
    "ns":"🔭","ss":"🌍","ems":"💰","tech":"⚙️",
    "lo":"🧠","ca":"🎨",
    "acc":"📈","bs":"💼","econ":"💹",
    "geo":"🗺️","hist":"📜","reli":"✝️",
    "it":"💻","cat":"🖥️","egd":"📏",
    "mechtech":"🔧","elecserv":"⚡","civiltech":"🏗️","agritech":"🚜",
    "drama":"🎭","music":"🎵","visart":"🖌️","design":"✏️",
    "cons":"🛒","hosp":"🍽️","tour":"✈️",
    "sportsc":"🏃",
}

# Per-grade subject availability
GRADE_SUBJECTS = {
    8:  ["eng","afr","isizulu","isixhosa","sesotho","setswana","math","ns","ss","ems","tech","lo","ca"],
    9:  ["eng","afr","isizulu","isixhosa","sesotho","setswana","math","ns","ss","ems","tech","lo","ca"],
    10: ["eng","afr","isizulu","isixhosa","sesotho","setswana","sepedi","xitsonga","tshivenda","siswati","isindebele",
         "lo","math","mlit","techmath","phy","techsci","ls","agri","ms","ns",
         "acc","bs","econ","geo","hist","reli",
         "it","cat","egd","mechtech","elecserv","civiltech","agritech",
         "drama","music","visart","design","cons","hosp","tour","sportsc"],
    11: ["eng","afr","isizulu","isixhosa","sesotho","setswana","sepedi","xitsonga","tshivenda","siswati","isindebele",
         "lo","math","mlit","techmath","phy","techsci","ls","agri","ms",
         "acc","bs","econ","geo","hist","reli",
         "it","cat","egd","mechtech","elecserv","civiltech","agritech",
         "drama","music","visart","design","cons","hosp","tour","sportsc"],
    12: ["eng","afr","isizulu","isixhosa","sesotho","setswana","sepedi","xitsonga","tshivenda","siswati","isindebele",
         "lo","math","mlit","techmath","phy","techsci","ls","agri","ms",
         "acc","bs","econ","geo","hist","reli",
         "it","cat","egd","mechtech","elecserv","civiltech","agritech",
         "drama","music","visart","design","cons","hosp","tour","sportsc"],
}

# NBT sections — 2 tests: AQL (Academic & Quantitative Literacy) + MAT
# stored as subject=nbt_aql/nbt_mat, grade=0
NBT_SECTIONS = {
    "nbt_aql": "NBT – Academic & Quantitative Literacy (AQL)",
    "nbt_mat": "NBT – Mathematics (MAT)",
}
NBT_ICONS = {
    "nbt_aql": "📖", "nbt_mat": "📐",
}

# ── MODELS ────────────────────────────────────────────────────────────────────

class User(db.Model):
    __tablename__ = "users"
    id       = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role     = db.Column(db.String(20), default="student")

class Material(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    title       = db.Column(db.String(200))
    filename    = db.Column(db.String(500))  # stores Cloudinary URL
    subject = db.Column(db.String(100), index=True)
    grade   = db.Column(db.Integer, index=True)
    uploaded_by = db.Column(db.String(100))
    downloads   = db.Column(db.Integer, default=0)


class Planner(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    title       = db.Column(db.String(200))
    description = db.Column(db.String(500))
    date        = db.Column(db.DateTime)
    subject     = db.Column(db.String(50))
    user = db.Column(db.String(100), index=True)

class Note(db.Model):
    id      = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text)
    subject = db.Column(db.String(50), index=True)
    grade   = db.Column(db.Integer)
    user    = db.Column(db.String(100), index=True)


class InstallCount(db.Model):
    id    = db.Column(db.Integer, primary_key=True)
    count = db.Column(db.Integer, default=0)

# ── HELPERS ───────────────────────────────────────────────────────────────────

ALLOWED_EXTENSIONS = {"pdf", "docx", "pptx", "doc", "ppt"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_icon(filename):
    # filename may now be a full Cloudinary URL — extract just the extension
    clean = filename.split("?")[0].split("/")[-1]
    ext = clean.rsplit(".", 1)[-1].lower() if "." in clean else ""
    return {"pdf": "📕", "doc": "📄", "docx": "📄", "ppt": "📊", "pptx": "📊"}.get(ext, "📁")

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect("/login")
        if session.get("username") != ADMIN_USERNAME and session.get("role") != "admin":
            return render_template("error.html", message="Access denied — admins only."), 403
        return f(*args, **kwargs)
    return decorated

def teacher_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect("/login")
        if session.get("role") != "teacher":
            return render_template("error.html", message="Access denied — teachers only."), 403
        return f(*args, **kwargs)
    return decorated

with app.app_context():
    db.create_all()

# ── ROUTES ────────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        role     = request.form.get("role", "student")
        if not username or not password:
            error = "Username and password are required."
        elif User.query.filter_by(username=username).first():
            error = "That username is already taken."
        else:
            db.session.add(User(username=username, password=generate_password_hash(password), role=role))
            db.session.commit()
            return redirect("/login")
    return render_template("register.html", error=error)

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        user = User.query.filter_by(username=request.form["username"].strip()).first()
        if user and check_password_hash(user.password, request.form["password"]):
            session["user"]     = user.username
            session["username"] = user.username
            session["role"]     = user.role
            return redirect("/dashboard")
        error = "Incorrect username or password."
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/dashboard", methods=["GET", "POST"])
@login_required
def dashboard():
    username = session["user"]
    role     = session["role"]
    today    = datetime.now().date()

    if request.method == "POST":
        try:
            task_date = datetime.fromisoformat(request.form["date"])
        except (ValueError, KeyError):
            task_date = datetime.now()
        db.session.add(Planner(
            title=request.form.get("title","").strip(),
            description=request.form.get("description","").strip(),
            date=task_date, user=username
        ))
        db.session.commit()
        return redirect("/dashboard")

    today_start = datetime.combine(today, datetime.min.time())
    today_end   = datetime.combine(today, datetime.max.time())

    # Fetch all and filter/sort in Python — avoids DB column type issues
    def parse_task_date(t):
        try:
            if isinstance(t.date, datetime):
                return t.date
            if t.date:
                return datetime.fromisoformat(str(t.date))
        except Exception:
            pass
        return None

    all_tasks     = Planner.query.filter_by(user=username).order_by(Planner.id).all()
    tasks_today   = sorted([t for t in all_tasks if parse_task_date(t) and today_start <= parse_task_date(t) <= today_end], key=parse_task_date)
    overdue_tasks = sorted([t for t in all_tasks if parse_task_date(t) and parse_task_date(t) < today_start], key=parse_task_date, reverse=True)

    total_downloads   = db.session.query(func.sum(Material.downloads)).scalar() or 0
    popular_materials = Material.query.order_by(Material.downloads.desc()).limit(5).all()

    is_admin = (username == ADMIN_USERNAME or role == "admin")

    return render_template("dashboard.html",
        username=username, role=role, is_admin=is_admin,
        tasks_today=tasks_today, overdue_tasks=overdue_tasks,
        total_downloads=total_downloads, popular_materials=popular_materials)

@app.route("/classes")
@login_required
def classes():
    return render_template("classes.html")

@app.route("/apply")
@login_required
def apply():
    return render_template("apply.html")

@app.route("/nbt")
@login_required
def nbt():
    materials = {
        "nbt_aql": Material.query.filter_by(subject="nbt_aql", grade=0).order_by(Material.id.desc()).all(),
        "nbt_mat": Material.query.filter_by(subject="nbt_mat", grade=0).order_by(Material.id.desc()).all(),
    }
    return render_template("nbt.html", materials=materials, get_file_icon=get_file_icon, NBT_SECTIONS=NBT_SECTIONS, NBT_ICONS=NBT_ICONS)

@app.route("/grade/<int:grade>")
@login_required
def grade(grade):
    if grade not in range(8, 13):
        return redirect("/classes")
    grade_codes = GRADE_SUBJECTS.get(grade, list(SUBJECTS.keys()))
    grade_subjects = {k: SUBJECTS[k] for k in grade_codes if k in SUBJECTS}

    # Build grouped subjects for the template
    GROUP_DEFS = [
        ("🗣️ Languages",      ["eng","afr","isizulu","isixhosa","sesotho","setswana","sepedi","xitsonga","tshivenda","siswati","isindebele"]),
        ("📊 Mathematics",    ["math","mlit","techmath"]),
        ("🔬 Sciences",       ["phy","techsci","ls","ns","agri","ms"]),
        ("💼 Commerce",       ["acc","bs","econ","ems"]),
        ("🌍 Humanities",     ["geo","hist","ss","reli"]),
        ("⚙️ Technology",     ["it","cat","egd","tech","mechtech","elecserv","civiltech","agritech"]),
        ("🎨 Arts & Culture", ["drama","music","visart","design","ca"]),
        ("🧠 Life & Consumer",["lo","cons","hosp","tour","sportsc"]),
    ]
    grouped = []
    for gname, codes in GROUP_DEFS:
        items = [(c, grade_subjects[c], SUBJECT_ICONS.get(c,"📘")) for c in codes if c in grade_subjects]
        if items:
            grouped.append((gname, items))

    return render_template("grade.html", grade=grade, subjects=grade_subjects,
                           icons=SUBJECT_ICONS, grouped=grouped)

@app.route("/subject/<int:grade>/<code>")
@login_required
def subject(grade, code):
    if code not in SUBJECTS:
        return redirect(f"/grade/{grade}")
    materials = Material.query.filter_by(subject=code, grade=grade).order_by(Material.downloads.desc()).all()
    return render_template("subject.html", grade=grade, subject=SUBJECTS.get(code), code=code,
                           materials=materials, get_file_icon=get_file_icon)

@app.route("/admin/fix-legacy-materials")
@admin_required
def fix_legacy_materials():
    bad = Material.query.filter(
        ~Material.filename.startswith("http")
    ).all()
    count = len(bad)
    for m in bad:
        db.session.delete(m)
    db.session.commit()
    return f"Deleted {count} legacy material(s) with no valid URL.", 200

@app.route("/download/<int:id>")
@login_required
def download(id):
    material = Material.query.get_or_404(id)
    material.downloads += 1
    db.session.commit()

    file_url = material.filename

    # Guard: legacy entry with no URL — nothing to serve
    if not file_url.startswith("http://") and not file_url.startswith("https://"):
        return render_template("error.html", message="This file is no longer available. Please ask your teacher to re-upload it."), 404

    # PDF: fetch from Cloudinary, rebrand on-the-fly
    if "/raw/upload/" in file_url or file_url.lower().split("?")[0].endswith(".pdf"):
        import urllib.request
        with urllib.request.urlopen(file_url) as resp:
            original_bytes = resp.read()
        branded_bytes = rebrand_pdf_bytes(original_bytes)
        download_name = file_url.split("/")[-1].split("?")[0]
        if not download_name.lower().endswith(".pdf"):
            download_name += ".pdf"
        return send_file(
            io.BytesIO(branded_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=download_name,
        )

    return redirect(file_url)

@app.route("/teacher")
@teacher_required
def teacher():
    materials = Material.query.filter_by(uploaded_by=session["user"]).order_by(Material.id.desc()).all()
    return render_template("teacher.html", materials=materials, subjects=SUBJECTS, get_file_icon=get_file_icon)

@app.route("/upload", methods=["GET", "POST"])
@teacher_required
def upload():
    error = None
    if request.method == "POST":
        title   = request.form.get("title","").strip()
        subject = request.form.get("subject","")
        grade   = request.form.get("grade","")
        file    = request.files.get("file")
        # NBT materials use grade=0
        is_nbt = subject in NBT_SECTIONS
        if is_nbt:
            grade = "0"
        if not title or not subject or not grade or not file or not file.filename:
            error = "Please fill in all fields and select a file."
        elif not allowed_file(file.filename):
            error = "Invalid file type. Please use PDF, DOC, DOCX, PPT, or PPTX."
        else:
            original_name = secure_filename(file.filename)
            base, ext = os.path.splitext(original_name)
            public_id = f"laurion/{base}_{int(datetime.now().timestamp())}"
            result = cloudinary.uploader.upload(
                file,
                resource_type="raw",
                public_id=public_id,
                use_filename=True,
                unique_filename=False,
            )
            file_url = result["secure_url"]
            db.session.add(Material(title=title, filename=file_url, subject=subject,
                                    grade=int(grade), uploaded_by=session["user"]))
            db.session.commit()
            if is_nbt:
                return redirect("/nbt")
            return redirect(f"/subject/{grade}/{subject}")
    return render_template("upload.html", error=error)

@app.route("/delete_material/<int:id>")
@teacher_required
def delete_material(id):
    material = Material.query.get_or_404(id)
    if material.uploaded_by != session["user"]:
        return render_template("error.html", message="You can only delete your own materials."), 403
    # Delete from Cloudinary
    try:
        parts = material.filename.split("/upload/")
        if len(parts) == 2:
            public_id = parts[1].split("?")[0]
            if public_id.startswith("v") and "/" in public_id:
                public_id = "/".join(public_id.split("/")[1:])
            cloudinary.uploader.destroy(public_id.rsplit(".", 1)[0], resource_type="raw")
    except Exception:
        pass
    was_nbt = material.subject in NBT_SECTIONS
    db.session.delete(material)
    db.session.commit()
    if was_nbt:
        return redirect("/nbt")
    return redirect("/teacher")

@app.route("/planner", methods=["GET", "POST"])
@login_required
def planner():
    if request.method == "POST":
        try:
            task_date = datetime.fromisoformat(request.form["date"])
        except (ValueError, KeyError):
            task_date = datetime.now()
        db.session.add(Planner(
            title=request.form.get("title","").strip(),
            description=request.form.get("description","").strip(),
            date=task_date, subject=request.form.get("subject",""),
            user=session["user"]
        ))
        db.session.commit()
        return redirect("/planner")
    # Fetch tasks safely — avoid any cast/ordering that depends on column type
    all_tasks = Planner.query.filter_by(user=session["user"]).order_by(Planner.id).all()
    # Sort in Python so we never touch the DB column type
    def safe_date(t):
        try:
            if isinstance(t.date, datetime):
                return t.date
            if t.date:
                return datetime.fromisoformat(str(t.date))
        except Exception:
            pass
        return datetime.min
    tasks = sorted(all_tasks, key=safe_date)
    return render_template("planner.html", tasks=tasks, subjects=SUBJECTS)

@app.route("/delete_task/<int:id>")
@login_required
def delete_task(id):
    task = Planner.query.get_or_404(id)
    if task.user != session["user"]:
        return render_template("error.html", message="Not authorised."), 403
    db.session.delete(task)
    db.session.commit()
    return redirect("/planner")

@app.route("/notes", methods=["GET", "POST"])
@login_required
def notes():
    username = session["user"]
    subject  = request.args.get("subject") or request.form.get("subject") or "math"
    grade    = int(request.args.get("grade") or request.form.get("grade") or 12)
    if subject not in SUBJECTS: subject = "math"
    if grade not in range(8, 13): grade = 12
    note = Note.query.filter_by(user=username, subject=subject, grade=grade).first()
    if request.method == "POST":
        content = request.form.get("content","")
        if note:
            note.content = content
        else:
            note = Note(content=content, subject=subject, grade=grade, user=username)
            db.session.add(note)
        db.session.commit()
    return render_template("notes.html",
        content=note.content if note else "",
        subject=subject, grade=grade, subjects=SUBJECTS)

@app.route("/sync-notes", methods=["POST"])
@login_required
def sync_notes():
    data  = request.get_json(silent=True) or {}
    subj  = data.get("subject","math")
    grade = int(data.get("grade", 12))
    note  = Note.query.filter_by(user=session["user"], subject=subj, grade=grade).first()
    if note:
        note.content = data.get("content","")
    else:
        db.session.add(Note(content=data.get("content",""), subject=subj, grade=grade, user=session["user"]))
    db.session.commit()
    return jsonify({"status": "ok"})

@app.route("/sync-planner", methods=["POST"])
@login_required
def sync_planner():
    data = request.get_json(silent=True) or {}
    try:
        task_date = datetime.fromisoformat(data.get("date",""))
    except (ValueError, TypeError):
        task_date = datetime.now()
    db.session.add(Planner(title=data.get("title","").strip(),
        description=data.get("description","").strip(), date=task_date, user=session["user"]))
    db.session.commit()
    return jsonify({"status": "ok"})

@app.route("/install-count")
def install_count():
    try:
        row = InstallCount.query.first()
        return jsonify({"count": row.count if row else 0})
    except Exception:
        return jsonify({"count": 0})

@app.route("/increment-install", methods=["POST"])
def increment_install():
    row = InstallCount.query.first()
    if not row:
        db.session.add(InstallCount(count=1))
    else:
        row.count += 1
    db.session.commit()
    return jsonify({"status": "ok"})

@app.route("/api/tasks")
@login_required
def api_tasks():
    tasks = Planner.query.filter_by(user=session["user"]).all()
    return jsonify([{"id":t.id,"title":t.title,"description":t.description,
                     "date":t.date.isoformat() if t.date else None} for t in tasks])

@app.route("/api/materials")
def api_materials():
    grade   = request.args.get("grade", type=int)
    subject = request.args.get("subject","")
    q = Material.query
    if grade:   q = q.filter_by(grade=grade)
    if subject: q = q.filter_by(subject=subject)
    items = q.order_by(Material.downloads.desc()).limit(50).all()
    return jsonify([{"id":m.id,"title":m.title,"subject":m.subject,
                     "grade":m.grade,"downloads":m.downloads,"filename":m.filename} for m in items])

@app.route("/api/notes")
@login_required
def api_notes():
    subject = request.args.get("subject","math")
    grade   = request.args.get("grade", 12, type=int)
    note    = Note.query.filter_by(user=session["user"], subject=subject, grade=grade).first()
    return jsonify({"content": note.content if note else ""})


@app.route("/migrate-db")
def migrate_db():
    try:
        with db.engine.connect() as conn:
            result = conn.execute(db.text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name='planner' AND column_name='date'"
            ))
            row = result.fetchone()
            if not row:
                return "Column not found — has the table been created?", 400
            col_type = row[0].lower()
            if "timestamp" in col_type or "date" in col_type:
                return f"✅ Column already correct type: {row[0]}. No migration needed.", 200
            conn.execute(db.text(
                "ALTER TABLE planner "
                "ALTER COLUMN date TYPE TIMESTAMP "
                "USING date::TIMESTAMP"
            ))
            conn.commit()
            return "✅ Migration complete — planner.date converted to TIMESTAMP.", 200
    except Exception as e:
        return f"❌ Migration failed: {e}", 500


# ── ADMIN PANEL ───────────────────────────────────────────────────────────────

@app.route("/admin")
@admin_required
def admin_panel():
    users        = User.query.order_by(User.id.desc()).all()
    user_count   = User.query.count()
    student_count= User.query.filter_by(role="student").count()
    teacher_count= User.query.filter_by(role="teacher").count()
    mat_count    = Material.query.count()
    total_dl     = db.session.query(func.sum(Material.downloads)).scalar() or 0
    return render_template("admin.html",
        users=users, user_count=user_count,
        student_count=student_count, teacher_count=teacher_count,
        mat_count=mat_count, total_downloads=total_dl)


@app.route("/admin/delete-user/<int:id>", methods=["POST"])
@admin_required
def admin_delete_user(id):
    user = User.query.get_or_404(id)
    if user.username == ADMIN_USERNAME:
        return render_template("error.html", message="Cannot delete the admin account."), 403
    Planner.query.filter_by(user=user.username).delete()
    Note.query.filter_by(user=user.username).delete()
    for mat in Material.query.filter_by(uploaded_by=user.username).all():
        try:
            parts = mat.filename.split("/upload/")
            if len(parts) == 2:
                public_id = parts[1].split("?")[0]
                if public_id.startswith("v") and "/" in public_id:
                    public_id = "/".join(public_id.split("/")[1:])
                cloudinary.uploader.destroy(public_id.rsplit(".", 1)[0], resource_type="raw")
        except Exception:
            pass
        db.session.delete(mat)
    db.session.delete(user)
    db.session.commit()
    return redirect("/admin")


@app.route("/admin/change-role/<int:id>", methods=["POST"])
@admin_required
def admin_change_role(id):
    user = User.query.get_or_404(id)
    new_role = request.form.get("role", "student")
    if new_role in ("student", "teacher", "admin"):
        user.role = new_role
        db.session.commit()
    return redirect("/admin")

@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", message="Page not found."), 404

@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", message="Something went wrong. Please try again."), 500

@app.route('/sw.js')
def service_worker():
    from flask import make_response, send_from_directory
    resp = make_response(send_from_directory('static', 'sw.js'))
    resp.headers['Service-Worker-Allowed'] = '/'
    resp.headers['Cache-Control']          = 'no-cache, no-store, must-revalidate'
    resp.headers['Content-Type']           = 'application/javascript'
    return resp

if __name__ == "__main__":
    app.run(debug=False)
