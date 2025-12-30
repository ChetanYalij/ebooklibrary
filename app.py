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

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL or "postgresql://chetan-yalij:3151@localhost:5432/ebooklib"
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
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    results = Book.query.filter(
        (Book.title.ilike(f"%{q}%")) |
        (Book.author.ilike(f"%{q}%"))
    ).limit(6).all()
    return jsonify([{"id": b.id, "title": b.title, "author": b.author} for b in results])

# =================== AUTH ROUTES ===================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        if User.query.filter_by(email=email).first():
            flash("Email already registered", "error")
            return redirect(url_for("register"))
        user = User(
            name=name,
            email=email,
            password=generate_password_hash(password),
            is_admin=False
        )
        db.session.add(user)
        db.session.commit()
        flash("Registration successful! Please login.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            session["user_id"] = user.id
            session["user_name"] = user.name
            session["user_email"] = user.email
            session["is_admin"] = user.is_admin
            
            flash("Login successful!", "success")
            if user.is_admin:
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("index"))
        flash("Invalid email or password", "error")
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
    category_stats = db.session.query(Book.category, func.count(Book.id)).group_by(Book.category).all()
    recent_books = Book.query.order_by(Book.id.desc()).limit(10).all()
    
    return render_template(
        "admin_dashboard.html",
        total_books=total_books,
        total_authors=total_authors,
        category_stats=category_stats,
        recent_books=recent_books
    )

@app.route("/admin/upload", methods=["GET", "POST"])
@admin_required
def upload_book():
    if request.method == "POST":
        title = request.form.get("title")
        author = request.form.get("author")
        description = request.form.get("description", "")
        category = request.form.get("category", "Uncategorized")

        if Book.query.filter_by(title=title, author=author).first():
            flash("This book already exists!", "error")
            return redirect(url_for("upload_book"))

        cover_url = None
        pdf_url = None

        # Cover upload
        cover = request.files.get("cover")
        if cover and cover.filename:
            try:
                res = cloudinary.uploader.upload(cover)
                cover_url = res["secure_url"]
            except Exception as e:
                flash(f"Cover upload failed: {str(e)}", "error")
                return redirect(url_for("upload_book"))

        # PDF upload (required)
        pdf = request.files.get("pdf")
        if not pdf or not pdf.filename:
            flash("PDF file is required!", "error")
            return redirect(url_for("upload_book"))
        
        try:
            pdf_res = cloudinary.uploader.upload(pdf, resource_type="raw")
            pdf_url = pdf_res["secure_url"]
        except Exception as e:
            flash(f"PDF upload failed: {str(e)}", "error")
            return redirect(url_for("upload_book"))

        # Save book
        book = Book(
            title=title,
            author=author,
            description=description,
            category=category,
            cover_url=cover_url,
            pdf_url=pdf_url
        )
        db.session.add(book)
        db.session.commit()
        flash("Book uploaded successfully!", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("upload.html")

@app.route("/admin/upload_json", methods=["POST"])
@admin_required
def upload_json():
    file = request.files.get("json_file")
    if not file or not file.filename.endswith(".json"):
        flash("Please upload a valid JSON file", "error")
        return redirect(url_for("upload_book"))

    try:
        data = json.load(file)
        added = 0
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
            added += 1
        db.session.commit()
        flash(f"{added} books uploaded from JSON successfully!", "success")
    except Exception as e:
        flash(f"JSON upload failed: {str(e)}", "error")
    
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
        
        # Optional: update cover if new one uploaded
        cover = request.files.get("cover")
        if cover and cover.filename:
            try:
                res = cloudinary.uploader.upload(cover)
                book.cover_url = res["secure_url"]
            except Exception as e:
                flash(f"Cover update failed: {str(e)}", "warning")
        
        db.session.commit()
        flash("Book updated successfully!", "success")
        return redirect(url_for("admin_dashboard"))
    
    return render_template("edit_book.html", book=book)

@app.route("/admin/delete/<int:book_id>", methods=["POST"])
@admin_required
def delete_book(book_id):
    book = Book.query.get_or_404(book_id)
    db.session.delete(book)
    db.session.commit()
    flash("Book deleted successfully!", "success")
    return redirect(url_for("admin_dashboard"))

# =================== RUN APP ===================
if __name__ == "__main__":
    app.run()