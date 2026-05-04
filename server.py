from flask import Flask, render_template, request, redirect, session, url_for, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from datetime import datetime
from sqlalchemy import func
import os

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "laurion-dev-key-change-in-production")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////tmp/laurion.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
if "postgresql" in DATABASE_URL and "sslmode" not in DATABASE_URL:
    DATABASE_URL += "?sslmode=require"

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

SUBJECTS = {
    "math": "Mathematics",
    "phy":  "Physical Science",
    "ls":   "Life Science",
    "geo":  "Geography",
    "acc":  "Accounting",
}
SUBJECT_ICONS = {
    "math": "📊", "phy": "⚛️", "ls": "🌿", "geo": "🌍", "acc": "📈",
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
    filename    = db.Column(db.String(200))
    subject     = db.Column(db.String(100))
    grade       = db.Column(db.Integer)
    uploaded_by = db.Column(db.String(100))
    downloads   = db.Column(db.Integer, default=0)

class Planner(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    title       = db.Column(db.String(200))
    description = db.Column(db.String(500))
    date        = db.Column(db.DateTime)
    subject     = db.Column(db.String(50))
    user        = db.Column(db.String(100))

class Note(db.Model):
    id      = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text)
    subject = db.Column(db.String(50))
    grade   = db.Column(db.Integer)
    user    = db.Column(db.String(100))

class InstallCount(db.Model):
    id    = db.Column(db.Integer, primary_key=True)
    count = db.Column(db.Integer, default=0)

# ── HELPERS ───────────────────────────────────────────────────────────────────

ALLOWED_EXTENSIONS = {"pdf", "docx", "pptx", "doc", "ppt"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_icon(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return {"pdf": "📕", "doc": "📄", "docx": "📄", "ppt": "📊", "pptx": "📊"}.get(ext, "📁")

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect("/login")
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

@app.before_request
def create_tables():
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
            session["user"] = user.username
            session["role"] = user.role
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

    tasks_today = Planner.query.filter(
        Planner.user == username,
        db.func.date(Planner.date) == today
    ).order_by(Planner.date).all()

    overdue_tasks = Planner.query.filter(
        Planner.user == username,
        Planner.date < datetime.combine(today, datetime.min.time())
    ).order_by(Planner.date.desc()).all()

    total_downloads   = db.session.query(func.sum(Material.downloads)).scalar() or 0
    popular_materials = Material.query.order_by(Material.downloads.desc()).limit(5).all()

    return render_template("dashboard.html",
        username=username, role=role,
        tasks_today=tasks_today, overdue_tasks=overdue_tasks,
        total_downloads=total_downloads, popular_materials=popular_materials)

@app.route("/classes")
@login_required
def classes():
    return render_template("classes.html")

@app.route("/grade/<int:grade>")
@login_required
def grade(grade):
    if grade not in range(8, 13):
        return redirect("/classes")
    return render_template("grade.html", grade=grade, subjects=SUBJECTS, icons=SUBJECT_ICONS)

@app.route("/subject/<int:grade>/<code>")
@login_required
def subject(grade, code):
    if code not in SUBJECTS:
        return redirect(f"/grade/{grade}")
    materials = Material.query.filter_by(subject=code, grade=grade).order_by(Material.downloads.desc()).all()
    return render_template("subject.html", grade=grade, subject=SUBJECTS.get(code), code=code,
                           materials=materials, get_file_icon=get_file_icon)

@app.route("/download/<int:id>")
@login_required
def download(id):
    material = Material.query.get_or_404(id)
    material.downloads += 1
    db.session.commit()
    return redirect(url_for("static", filename="uploads/" + material.filename))

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
        if not title or not subject or not grade or not file or not file.filename:
            error = "Please fill in all fields and select a file."
        elif not allowed_file(file.filename):
            error = "Invalid file type. Please use PDF, DOC, DOCX, PPT, or PPTX."
        else:
            base, ext = os.path.splitext(secure_filename(file.filename))
            filename  = f"{base}_{int(datetime.now().timestamp())}{ext}"
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            db.session.add(Material(title=title, filename=filename, subject=subject,
                                    grade=int(grade), uploaded_by=session["user"]))
            db.session.commit()
            return redirect(f"/subject/{grade}/{subject}")
    return render_template("upload.html", error=error)

@app.route("/delete_material/<int:id>")
@teacher_required
def delete_material(id):
    material = Material.query.get_or_404(id)
    if material.uploaded_by != session["user"]:
        return render_template("error.html", message="You can only delete your own materials."), 403
    path = os.path.join(app.config["UPLOAD_FOLDER"], material.filename)
    if os.path.exists(path):
        os.remove(path)
    db.session.delete(material)
    db.session.commit()
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
    tasks = Planner.query.filter_by(user=session["user"]).order_by(Planner.date).all()
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
    row = InstallCount.query.first()
    return jsonify({"count": row.count if row else 0})

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

@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", message="Page not found."), 404

@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", message="Something went wrong. Please try again."), 500

if __name__ == "__main__":
    app.run(debug=False)
