from flask import Flask, render_template, request, redirect, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask import flash
import os

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

app = Flask(__name__)

# 🔐 Secret key
app.secret_key = "supersecretkey"

# 🗄️ Database config
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
if app.config['SQLALCHEMY_DATABASE_URI']:
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace("postgres://", "postgresql://")

# 📁 Upload config
UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)

# ======================
# 🧠 MODELS
# ======================

class User(db.Model):
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


# ======================
# 🏠 ROUTES
# ======================

@app.route("/")
def home():
    return render_template("index.html")


# ======================
# 🔐 AUTH
# ======================

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        role = request.form["role"]

        # 🔍 check if user already exists
        existing_user = User.query.filter_by(username=username).first()

        if existing_user:
            return "Username already exists ⚠️ Try another one."

        hashed_password = generate_password_hash(password)

        new_user = User(
            username=username,
            password=hashed_password,
            role=role
        )

        db.session.add(new_user)
        db.session.commit()

        return redirect("/login")

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            session["user"] = username
            session["role"] = user.role
            return redirect("/dashboard")
        else:
            return "Invalid credentials"

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/")


# ======================
# 📊 DASHBOARD
# ======================

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/login")

    role = session.get("role")
    username = session.get("user")

    if role == "teacher":
        materials = Material.query.filter_by(
            uploaded_by=username
        ).order_by(Material.id.desc()).limit(5).all()

        return render_template(
            "dashboard.html",
            role=role,
            username=username,
            total=len(materials),
            recent_materials=materials
        )

    else:
        materials = Material.query.order_by(
            Material.id.desc()
        ).limit(5).all()

        return render_template(
            "dashboard.html",
            role=role,
            username=username,
            recent_materials=materials,
            subjects=SUBJECTS
        )
    
# ======================
# 📚 CLASSES & SUBJECTS
# ======================

@app.route("/classes")
def classes():
    if "user" not in session:
        return redirect("/login")

    return render_template("classes.html")

#grade
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

#subject
@app.route("/subject/<int:grade>/<code>")
def subject(grade, code):
    if "user" not in session:
        return redirect("/login")

    subject_name = SUBJECTS.get(code)

    materials = Material.query.filter_by(
        subject=code,
        grade=grade
    ).all()

    return render_template(
        "subject.html",
        grade=grade,
        subject=subject_name,
        materials=materials,
        get_file_icon=get_file_icon
    )

# ======================
# 📁 UPLOAD SYSTEM
# ======================

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

        if not file or not title or not subject or not grade:
            flash("⚠️ Please fill in all fields")
            return redirect("/upload")

        if file:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(filepath)

            new_material = Material(
                title=title,
                filename=filename,
                subject=subject,
                grade=int(grade),
                uploaded_by=session["user"]
            )

            db.session.add(new_material)
            db.session.commit()

            flash("Material uploaded successfully!")
            return redirect(f"/subject/{grade}/{subject}")

    #  THIS runs for GET
    return render_template("upload.html")

#teacher
@app.route("/teacher")
def teacher_dashboard():
    if "user" not in session:
        return redirect("/login")

    if session.get("role") != "teacher":
        return "Access denied 🚫"

    materials = Material.query.filter_by(
        uploaded_by=session["user"]
    ).all()

    # 📊 analytics
    total_materials = len(materials)
    subjects = set([m.subject for m in materials])
    grades = set([m.grade for m in materials])
    file_types = set([m.filename.split('.')[-1] for m in materials])

    return render_template(
        "teacher.html",
        materials=materials,
        subjects=SUBJECTS,
        total_materials=total_materials,
        subject_count=len(subjects),
        grade_count=len(grades),
        file_type_count=len(file_types),
        get_file_icon=get_file_icon
    )

#delete
@app.route("/delete/<int:id>")
def delete(id):
    if "user" not in session:
        return redirect("/login")

    material = Material.query.get_or_404(id)

    if material.uploaded_by != session["user"]:
        return "Not allowed 🚫"

    # delete file from folder
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], material.filename)
    if os.path.exists(filepath):
        os.remove(filepath)

    db.session.delete(material)
    db.session.commit()

    return redirect("/teacher")

def get_file_icon(filename):
    ext = filename.split(".")[-1].lower()

    if ext == "pdf":
        return "📕"
    elif ext in ["doc", "docx"]:
        return "📄"
    elif ext in ["ppt", "pptx"]:
        return "📊"
    else:
        return "📁"
    
# ======================
# ▶️ RUN
# ======================

if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)