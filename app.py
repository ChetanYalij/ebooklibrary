import os
import json
from functools import wraps
from flask import (
    Flask, render_template, request, session,
    flash, redirect, url_for, jsonify
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from werkzeug.security import generate_password_hash, check_password_hash
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

# ------------------- Load .env -------------------
load_dotenv()

# ------------------- Flask Setup -------------------
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-this-secret-key")

# ------------------- ADMIN CONFIG -------------------
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

# ------------------- Decorators -------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_email" not in session:
            flash("Please login first", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_email" not in session:
            flash("Login required", "error")
            return redirect(url_for("login"))
        if not session.get("is_admin"):
            flash("Admin access only", "error")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated_function

# ------------------- Cloudinary -------------------
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

# ------------------- Database -------------------
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL or \
    "postgresql://chetan-yalij:3151@localhost:5432/ebooklib"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 300
}

db = SQLAlchemy(app)

# ------------------- MODELS -------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200))
    name = db.Column(db.String(100))
    is_admin = db.Column(db.Boolean, default=False)

class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(50), default="Uncategorized")
    cover_url = db.Column(db.String(500))
    pdf_url = db.Column(db.String(500))

# ------------------- Create Tables + Admin -------------------
with app.app_context():
    db.create_all()
    if ADMIN_EMAIL and ADMIN_PASSWORD:
        admin = User.query.filter_by(email=ADMIN_EMAIL).first()
        if not admin:
            admin = User(
                email=ADMIN_EMAIL,
                password=generate_password_hash(ADMIN_PASSWORD),
                is_admin=True
            )
            db.session.add(admin)
            db.session.commit()

# =================== PUBLIC ROUTES ===================
@app.route("/")
def index():
    books = Book.query.all()
    return render_template("index.html", books=books)

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

@app.route("/book/<int:book_id>")
def book_detail(book_id):
    book = Book.query.get_or_404(book_id)
    return render_template("book_detail.html", book=book)

# =================== AUTH (NORMAL USERS) ===================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        user = User.query.filter_by(email=email, is_admin=False).first()
        if not user or not check_password_hash(user.password, password):
            flash("Invalid credentials", "error")
            return redirect(url_for("login"))
        session["user_id"] = user.id
        session["user_email"] = user.email
        session["is_admin"] = False
        return redirect(url_for("index"))
    return render_template("login.html")

# =================== ADMIN LOGIN ===================
@app.route("/ebooklibrary-admin-9382-login", methods=["GET", "POST"])
def secret_admin_login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        user = User.query.filter_by(email=email, is_admin=True).first()
        if not user or not check_password_hash(user.password, password):
            flash("Invalid admin credentials", "error")
            return redirect(request.url)
        session["user_id"] = user.id
        session["user_email"] = user.email
        session["is_admin"] = True
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# =================== SEARCH ===================
@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    results = Book.query.filter(
        (Book.title.ilike(f"%{q}%")) |
        (Book.author.ilike(f"%{q}%"))
    ).limit(6).all()
    return jsonify([{"id": b.id, "title": b.title, "author": b.author} for b in results])

@app.route("/search")
def search():
    query = request.args.get("query", "")
    books = []
    if query:
        books = Book.query.filter(
            (Book.title.ilike(f"%{query}%")) |
            (Book.author.ilike(f"%{query}%"))
        ).all()
    return render_template("search_results.html", books=books, query=query)

# =================== REGISTER ===================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        confirm = request.form.get("confirm_password")
        if not email or not password or not confirm:
            flash("All fields are required", "error")
            return redirect(url_for("register"))
        if password != confirm:
            flash("Passwords do not match", "error")
            return redirect(url_for("register"))
        if User.query.filter_by(email=email).first():
            flash("Email already exists", "error")
            return redirect(url_for("register"))
        user = User(email=email, password=generate_password_hash(password), is_admin=False)
        db.session.add(user)
        db.session.commit()
        flash("Registration successful. Please login.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

# =================== ADMIN DASHBOARD ===================
@app.route("/admin")
@admin_required
def admin_dashboard():
    total_books = Book.query.count()
    total_authors = db.session.query(Book.author).distinct().count()
    category_stats = db.session.query(Book.category, func.count(Book.id)).group_by(Book.category).all()
    recent_books = Book.query.order_by(Book.id.desc()).limit(5).all()
    return render_template(
        "admin_dashboard.html",
        total_books=total_books,
        total_authors=total_authors,
        category_stats=category_stats,
        recent_books=recent_books
    )

# =================== UPLOAD BOOK ===================
@app.route("/upload", methods=["GET", "POST"])
@admin_required
def upload():
    if request.method == "POST":
        title = request.form["title"]
        author = request.form["author"]
        description = request.form.get("description", "")
        category = request.form.get("category", "Uncategorized")

        if Book.query.filter_by(title=title, author=author).first():
            flash("This book already exists!", "error")
            return redirect(url_for("upload"))

        cover_url = None
        cover = request.files.get("cover")
        if cover and cover.filename:
            res = cloudinary.uploader.upload(cover)
            cover_url = res["secure_url"]

        pdf = request.files.get("pdf")
        if not pdf or not pdf.filename:
            flash("PDF file is required!", "error")
            return redirect(url_for("upload"))

        pdf_res = cloudinary.uploader.upload(pdf, resource_type="raw")

        book = Book(
            title=title,
            author=author,
            description=description,
            category=category,
            cover_url=cover_url,
            pdf_url=pdf_res["secure_url"]
        )

        db.session.add(book)
        db.session.commit()
        flash("Book uploaded successfully!", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("upload.html")

# =================== UPLOAD JSON ===================
@app.route("/upload_json", methods=["POST"])
@admin_required
def upload_json():
    file = request.files.get("json_file")
    if not file or not file.filename.endswith(".json"):
        flash("Invalid JSON file", "error")
        return redirect(url_for("upload"))

    data = json.load(file)
    for b in data:
        if not b.get("title") or not b.get("author"):
            continue
        if Book.query.filter_by(title=b["title"], author=b["author"]).first():
            continue
        db.session.add(Book(
            title=b["title"],
            author=b["author"],
            description=b.get("description", ""),
            category=b.get("category", "Uncategorized"),
            cover_url=b.get("cover_url"),
            pdf_url=b.get("pdf_url")
        ))

    db.session.commit()
    flash("JSON uploaded successfully!", "success")
    return redirect(url_for("admin_dashboard"))

# =================== RUN ===================
if __name__ == "__main__":
    app.run(debug=True)
