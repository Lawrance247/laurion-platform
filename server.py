from flask import Flask, render_template, request, redirect, session, flash, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from datetime import datetime
from sqlalchemy import func
import os

# ======================
# 🎯 APP SETUP
# ======================

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ======================
# 🗄️ DATABASE CONFIG (POSTGRESQL ONLY)
# ======================

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

    # FORCE SSL (CRITICAL FOR RENDER)
    if "sslmode" not in DATABASE_URL:
        DATABASE_URL += "?sslmode=require"
else:
    DATABASE_URL = "sqlite:////tmp/fallback.db"

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ✅ CREATE TABLES ON START (SAFE)
@app.before_request
def create_tables():
    db.create_all()

# ======================
# 📁 UPLOAD CONFIG
# ======================

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ======================
# 📚 SUBJECT DATA
# ======================

SUBJECTS = {
    "math": "Mathematics",
    "phy": "Physical Science",
    "ls": "Life Science",
    "geo": "Geography",
    "acc": "Accounting"
}

SUBJECT_ICONS = {
    "math": "📊",
    "phy": "⚛️",
    "ls": "🌿",
    "geo": "🌍",
    "acc": "📈"
}

# ======================
# 🧠 MODELS
# ======================

class User(db.Model):
    __tablename__="users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default="student")


class Material(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    filename = db.Column(db.String(200))
    subject = db.Column(db.String(100))
    grade = db.Column(db.Integer)
    uploaded_by = db.Column(db.String(100))
    downloads = db.Column(db.Integer, default=0)


class Planner(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    description = db.Column(db.String(500))
    date = db.Column(db.DateTime)
    subject = db.Column(db.String(50))
    material_id = db.Column(db.Integer)
    role = db.Column(db.String(20))
    user = db.Column(db.String(100))


class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text)
    subject = db.Column(db.String(50))
    grade = db.Column(db.Integer)
    user = db.Column(db.String(100))

# ======================
# 🏠 ROUTES
# ======================

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/download/<int:id>")
def download(id):
    material = Material.query.get(id)

    if not material:
        return "File not found"

    material.downloads += 1
    db.session.commit()

    return redirect(url_for('static', filename='uploads/' + material.filename))


@app.route("/teacher")
def teacher():
    if "user" not in session:
        return redirect("/login")

    if session.get("role") != "teacher":
        return "Access denied 🚫"

    materials = Material.query.filter_by(uploaded_by=session["user"]).all()

    return render_template(
        "teacher.html",
        materials=materials,
        subjects=SUBJECTS,
        get_file_icon=get_file_icon
    )


@app.route("/delete_material/<int:id>")
def delete_material(id):
    material = Material.query.get(id)

    if not material:
        return "Not found"

    if material.uploaded_by != session.get("user"):
        return "Unauthorized 🚫"

    file_path = os.path.join(app.config["UPLOAD_FOLDER"], material.filename)

    if os.path.exists(file_path):
        os.remove(file_path)

    db.session.delete(material)
    db.session.commit()

    return redirect("/teacher")


# ======================
# 🔐 AUTH
# ======================

@app.route("/register", methods=["GET", "POST"])
def register():
    error = None

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        role = request.form["role"]

        existing = User.query.filter_by(username=username).first()

        if existing:
            error = "Username already exists"
        else:
            hashed = generate_password_hash(password)
            db.session.add(User(username=username, password=hashed, role=role))
            db.session.commit()
            return redirect("/login")

    return render_template("register.html", error=error)


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        user = User.query.filter_by(
            username=request.form["username"]
        ).first()

        if user and check_password_hash(user.password, request.form["password"]):
            session["user"] = user.username
            session["role"] = user.role
            return redirect("/dashboard")
        else:
            error = "Invalid username or password"

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ======================
# 📊 DASHBOARD
# ======================

@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "user" not in session:
        return redirect("/login")

    username = session["user"]
    role = session["role"]

    if request.method == "POST":
        db.session.add(Planner(
            title=request.form["title"],
            description=request.form["description"],
            date = datetime.fromisoformat(request.form["date"]),
            role=role,
            user=username
        ))
        db.session.commit()

    materials = Material.query.order_by(Material.id.desc()).limit(5).all()
    today = datetime.now().date()

    tasks_today = Planner.query.filter(
        Planner.user == username,
        db.func.date(Planner.date) == today
    ).all()

    overdue_tasks = Planner.query.filter(
        Planner.user == username,
        Planner.date < datetime.now()
    ).all()

    total_downloads = db.session.query(
        func.sum(Material.downloads)
    ).scalar() or 0

    popular = Material.query.order_by(
        Material.downloads.desc()
    ).limit(5).all()

    return render_template(
        "dashboard.html",
        username=username,
        role=role,
        tasks_today=tasks_today,
        overdue_tasks=overdue_tasks,
        recent_materials=materials,
        total_downloads=total_downloads,
        popular_materials=popular
    )


# ======================
# 📚 NAVIGATION
# ======================

@app.route("/classes")
def classes():
    if "user" not in session:
        return redirect("/login")
    return render_template("classes.html")


@app.route("/grade/<int:grade>")
def grade(grade):
    if "user" not in session:
        return redirect("/login")

    return render_template(
        "grade.html",
        grade=grade,
        subjects=SUBJECTS,
        icons=SUBJECT_ICONS
    )


@app.route("/subject/<int:grade>/<code>")
def subject(grade, code):
    if "user" not in session:
        return redirect("/login")

    materials = Material.query.filter_by(subject=code, grade=grade).all()

    return render_template(
        "subject.html",
        grade=grade,
        subject=SUBJECTS.get(code),
        materials=materials,
        get_file_icon=get_file_icon,
        code=code
    )


# ======================
# 📁 UPLOAD
# ======================

ALLOWED_EXTENSIONS = {"pdf", "docx", "pptx"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/upload", methods=["GET", "POST"])
def upload():
    if "user" not in session:
        return redirect("/login")

    if session.get("role") != "teacher":
        return "Access denied 🚫"

    if request.method == "POST":
        file = request.files["file"]
        title = request.form["title"]
        subject = request.form["subject"]
        grade = request.form["grade"]

        if not file or not title:
            flash("Fill all fields")
            return redirect("/upload")

        if not allowed_file(file.filename):
            flash("Invalid file type")
            return redirect("/upload")

        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        db.session.add(Material(
            title=title,
            filename=filename,
            subject=subject,
            grade=int(grade),
            uploaded_by=session["user"]
        ))

        db.session.commit()

        return redirect(f"/subject/{grade}/{subject}")

    return render_template("upload.html")


# ======================
# 📅 PLANNER
# ======================

@app.route("/planner", methods=["GET", "POST"])
def planner():
    if "user" not in session:
        return redirect("/login")

    if request.method == "POST":
        db.session.add(Planner(
            title=request.form["title"],
            description=request.form["description"],
            date=request.form["date"],
            subject=request.form.get("subject"),
            material_id=request.form.get("material"),
            role=session["role"],
            user=session["user"]
        ))
        db.session.commit()

    tasks = Planner.query.filter_by(user=session["user"]).all()
    materials = Material.query.all()

    return render_template(
        "planner.html",
        tasks=tasks,
        materials=materials,
        subjects=SUBJECTS
    )


@app.route("/delete_task/<int:id>")
def delete_task(id):
    task = Planner.query.get(id)

    if not task:
        return "Not found"

    db.session.delete(task)
    db.session.commit()
    return redirect("/planner")


# ======================
# 📝 NOTES
# ======================

@app.route("/notes", methods=["GET", "POST"])
def notes():
    if "user" not in session:
        return redirect("/login")

    username = session["user"]
    subject = request.args.get("subject") or request.form.get("subject") or "math"
    grade = int(request.args.get("grade") or request.form.get("grade") or 12)

    note = Note.query.filter_by(user=username, subject=subject, grade=grade).first()

    if request.method == "POST":
        content = request.form["content"]

        if note:
            note.content = content
        else:
            note = Note(content=content, subject=subject, grade=grade, user=username)
            db.session.add(note)

        db.session.commit()

    content = note.content if note else ""

    return render_template("notes.html", content=content, subject=subject, grade=grade)

@app.route("/sync-notes", methods=["POST"])
def sync_notes():
    if "user" not in session:
        return {"error": "Unauthorized"}, 403

    data = request.get_json()

    note = Note.query.filter_by(
        user=session["user"],
        subject=data["subject"],
        grade=data["grade"]
    ).first()

    if note:
        note.content = data["content"]
    else:
        db.session.add(Note(
            content=data["content"],
            subject=data["subject"],
            grade=data["grade"],
            user=session["user"]
        ))

    db.session.commit()
    return {"status": "ok"}

@app.route("/sync-planner", methods=["POST"])
def sync_planner():
    if "user" not in session:
        return {"error": "Unauthorized"}, 403

    data = request.get_json()

    db.session.add(Planner(
        title=data["title"],
        description=data["description"],
        date=datetime.fromisoformat(data["date"]),
        user=session["user"]
    ))

    db.session.commit()
    return {"status": "ok"}
# ======================
# 🧰 UTIL
# ======================

def get_file_icon(filename):
    ext = filename.split(".")[-1].lower()
    if ext == "pdf":
        return "📕"
    elif ext in ["doc", "docx"]:
        return "📄"
    elif ext in ["ppt", "pptx"]:
        return "📊"
    return "📁"


# ======================
# 🚀 START
# ======================

if __name__ == "__main__":
    app.run()