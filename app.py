import os
from functools import wraps
from flask import (
    Flask, render_template, request, session,
    flash, redirect, url_for, jsonify, abort
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, text
from sqlalchemy.exc import OperationalError
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

# ================== LOAD ENV ==================
load_dotenv()

# ================== APP SETUP ==================
app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.getenv("SECRET_KEY", "change-this")

# ================== ADMIN CONFIG ==================
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

# ================== DATABASE==================
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL not set")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if "sslmode" not in DATABASE_URL:
    DATABASE_URL += "?sslmode=require"

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
}

db = SQLAlchemy(app)

# ================== CLOUDINARY ==================
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

# ================== MODELS ==================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=False)

    def check_password(self, password_input):
        return check_password_hash(self.password, password_input)

class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(100))
    cover_url = db.Column(db.String(500))
    pdf_url = db.Column(db.String(500))

# ================== DECORATORS ==================
def login_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if "user_id" not in session:
            flash("Login required", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrap

def admin_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        try:
            user = User.query.get(session["user_id"])
        except OperationalError:
            db.session.rollback()
            return redirect(url_for("login"))

        if not user or not user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return wrap

# ================== INIT DB + ADMIN ==================
with app.app_context():
    db.session.execute(text("SELECT 1"))
    db.create_all()

    if ADMIN_EMAIL and ADMIN_PASSWORD:
        admin = User.query.filter_by(email=ADMIN_EMAIL).first()
        if not admin:
            admin = User(
                name="Admin",
                email=ADMIN_EMAIL,
                password=generate_password_hash(ADMIN_PASSWORD),
                is_admin=True
            )
            db.session.add(admin)
            db.session.commit()

# ================== PUBLIC ROUTES ==================
@app.route("/")
def index():
    books = Book.query.order_by(Book.id.desc()).all()
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

# ================== CATEGORY ==================
@app.route("/category/<category_name>")
def category_books(category_name):
    books = Book.query.filter(
        Book.category.ilike(f"%{category_name}%")
    ).all()

    return render_template(
        "categories.html",
        books=books,
        category=category_name
    )

# ================== SEARCH ==================
@app.route("/search")
def search():
    query = request.args.get("query", "").strip()

    if not query:
        return redirect(url_for("index"))

    search = f"%{query}%"

    books = Book.query.filter(
        Book.title.ilike(search) |
        Book.author.ilike(search) |
        Book.category.ilike(search) |
        Book.description.ilike(search)
    ).order_by(Book.id.desc()).all()

    return render_template(
        "search_page.html",
        books=books,
        query=query
    )

@app.route("/api/search")
def api_search():
    query = request.args.get("q", "").strip()

    if not query or len(query) < 2:
        return jsonify([])

    search = f"%{query}%"

    books = Book.query.filter(
        Book.title.ilike(search) |
        Book.author.ilike(search) |
        Book.category.ilike(search)
    ).order_by(Book.id.desc()).limit(10).all()

    return jsonify([
        {
            "id": b.id,
            "title": b.title,
            "author": b.author,
            "category": b.category,
            "cover": b.cover_url,
            "pdf": b.pdf_url
        } for b in books
    ])

# ================== READ ==================
@app.route("/read/<int:book_id>")
@login_required
def read_book(book_id):
    book = Book.query.get_or_404(book_id)
    return render_template("book_detail.html", book=book)

# ================== AUTH ==================
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
        email = request.form["email"]
        password = request.form["password"]
        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            session["user_id"] = user.id
            session["user_name"] = user.name
            session["is_admin"] = user.is_admin
            flash("Login successful!", "success")
            return redirect(url_for("index"))

        flash("Invalid email or password.", "error")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully", "success")
    return redirect(url_for("index"))

# ================== ADMIN ==================
@app.route("/admin")
@admin_required
def admin_dashboard():
    total_books = Book.query.count()
    total_authors = db.session.query(Book.author).distinct().count()

    category_stats = db.session.query(
        func.coalesce(Book.category, "Uncategorized"),
        func.count(Book.id)
    ).group_by(func.coalesce(Book.category, "Uncategorized")).all()

    recent_books = Book.query.order_by(Book.id.desc()).limit(10).all()

    return render_template(
        "admin_dashboard.html",
        total_books=total_books,
        total_authors=total_authors,
        category_stats=category_stats,
        recent_books=recent_books
    )

# ================== ADMIN UPLOAD ==================
@app.route("/admin/upload", methods=["GET", "POST"])
@admin_required
def upload_book():
    if request.method == "POST":
        cover_url = None

        cover_file = request.files.get("cover")
        if cover_file and cover_file.filename != "":
            cover = cloudinary.uploader.upload(cover_file)
            cover_url = cover["secure_url"]

        pdf = cloudinary.uploader.upload(
            request.files["pdf"],
            resource_type="raw"
        )

        book = Book(
            title=request.form["title"],
            author=request.form["author"],
            description=request.form.get("description", ""),
            category=request.form.get("category", "General"),
            cover_url=cover_url,
            pdf_url=pdf["secure_url"]
        )
        db.session.add(book)
        db.session.commit()

        flash("Book uploaded successfully", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("upload.html")

@app.route("/admin/delete/<int:book_id>", methods=["POST"])
@admin_required
def delete_book(book_id):
    book = Book.query.get_or_404(book_id)
    db.session.delete(book)
    db.session.commit()
    flash("Book deleted successfully", "success")
    return redirect(url_for("admin_dashboard"))

# ================== EDIT ==================
@app.route("/admin/edit-book/<int:book_id>", methods=["GET", "POST"])
@admin_required
def edit_book_pdf(book_id):
    book = Book.query.get_or_404(book_id)

    if request.method == "POST":
        book.title = request.form["title"]
        book.author = request.form["author"]
        book.category = request.form["category"]
        db.session.commit()
        flash("Book updated", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("edit_book_details.html", book=book)

# ================== UPDATE ==================
@app.route("/admin/update-book/<int:book_id>", methods=["POST"])
@admin_required
def update_book(book_id):
    book = Book.query.get_or_404(book_id)

    book.title = request.form["title"]
    book.author = request.form["author"]
    book.description = request.form.get("description", "")
    book.category = request.form.get("category", book.category)

    cover_file = request.files.get("cover_file")
    if cover_file and cover_file.filename != "":
        upload = cloudinary.uploader.upload(cover_file)
        book.cover_url = upload["secure_url"]

    db.session.commit()
    flash("Book updated successfully", "success")
    return redirect(url_for("admin_dashboard"))

# ================== ERRORS ==================
@app.errorhandler(403)
def forbidden(e):
    return "<h1>403 - Access Denied</h1>", 403

@app.errorhandler(404)
def not_found(e):
    return "<h1>404 - Page Not Found</h1>", 404

# ================== RUN ==================
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)