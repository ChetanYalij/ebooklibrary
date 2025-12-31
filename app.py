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
app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.getenv("SECRET_KEY", "change-this-secret-key")

# ------------------- ADMIN CONFIG -------------------
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

# ------------------- Decorators -------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Login required", "error")
            return redirect(url_for("login"))

        user = User.query.get(session["user_id"])
        if not user or not user.is_admin:
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

if DATABASE_URL and "sslmode" not in DATABASE_URL:
    DATABASE_URL += "?sslmode=require"

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

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
                name="Admin",
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

@app.route("/search")
def search():
    query = request.args.get("query", "").strip()
    books = []

    if query:
        books = Book.query.filter(
            (Book.title.ilike(f"%{query}%")) |
            (Book.author.ilike(f"%{query}%"))
        ).all()

    return render_template("search_results.html", books=books, query=query)

@app.route("/api/search")
def api_search():
    q = request.args.get("q", "")
    results = Book.query.filter(
        (Book.title.ilike(f"%{q}%")) |
        (Book.author.ilike(f"%{q}%"))
    ).limit(5).all()

    return jsonify([
        {"id": b.id, "title": b.title, "author": b.author}
        for b in results
    ])

# =================== AUTH ROUTES ===================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        if User.query.filter_by(email=request.form["email"]).first():
            flash("Email already exists", "error")
            return redirect(url_for("register"))

        user = User(
            name=request.form["name"],
            email=request.form["email"],
            password=generate_password_hash(request.form["password"])
        )
        db.session.add(user)
        db.session.commit()
        flash("Registered successfully", "success")
        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(email=request.form["email"]).first()
        if user and check_password_hash(user.password, request.form["password"]):
            session["user_id"] = user.id
            session["is_admin"] = user.is_admin

            if user.is_admin:
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("index"))

        flash("Invalid credentials", "error")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully", "success")
    return redirect(url_for("index"))

# =================== ADMIN ROUTES ===================
@app.route("/admin")
@admin_required
def admin_dashboard():
    total_books = Book.query.count()
    total_authors = db.session.query(Book.author).distinct().count()
    category_stats = db.session.query(
        Book.category, func.count(Book.id)
    ).group_by(Book.category).all()
    recent_books = Book.query.order_by(Book.id.desc()).limit(10).all()

    return render_template(
        "admin_dashboard.html",
        total_books=total_books,
        total_authors=total_authors,
        category_stats=category_stats,
        recent_books=recent_books
    )

@app.route("/admin/books")
@admin_required
def admin_books():
    books = Book.query.all()
    return render_template("admin_books.html", books=books)

@app.route("/admin/upload", methods=["GET", "POST"])
@admin_required
def upload_book():
    if request.method == "POST":
        cover_url = None

        if request.files.get("cover"):
            cover_res = cloudinary.uploader.upload(request.files["cover"])
            cover_url = cover_res["secure_url"]

        pdf_res = cloudinary.uploader.upload(
            request.files["pdf"], resource_type="raw"
        )

        book = Book(
            title=request.form["title"],
            author=request.form["author"],
            description=request.form.get("description", ""),
            category=request.form.get("category", "Uncategorized"),
            cover_url=cover_url,
            pdf_url=pdf_res["secure_url"]
        )

        db.session.add(book)
        db.session.commit()
        flash("Book uploaded successfully", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("upload.html")

@app.route("/admin/upload_json", methods=["POST"])
@admin_required
def upload_json():
    file = request.files.get("json_file")
    data = json.load(file)

    for b in data:
        if not Book.query.filter_by(title=b["title"]).first():
            db.session.add(Book(**b))

    db.session.commit()
    flash("JSON upload completed", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/edit/<int:book_id>", methods=["GET", "POST"])
@admin_required
def edit_book(book_id):
    book = Book.query.get_or_404(book_id)

    if request.method == "POST":
        book.title = request.form["title"]
        book.author = request.form["author"]
        book.description = request.form.get("description", "")
        book.category = request.form.get("category", "Uncategorized")
        db.session.commit()
        flash("Book updated", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("edit_book.html", book=book)

@app.route("/admin/delete/<int:book_id>", methods=["POST"])
@admin_required
def delete_book(book_id):
    book = Book.query.get_or_404(book_id)
    db.session.delete(book)
    db.session.commit()
    flash("Book deleted successfully", "success")
    return redirect(url_for("admin_dashboard"))

# =================== RUN ===================
if __name__ == "__main__":
    app.run(debug=True)
