import os
import json
from functools import wraps
from flask import (
    Flask, render_template, request, session,
    flash, redirect, url_for, jsonify
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

# ------------------- Load .env -------------------
load_dotenv()

# ------------------- Flask Setup -------------------
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'change-this-secret-key')

# ------------------- ADMIN CONFIG -------------------
ADMIN_EMAIL = "chetanyalij3151@gmail.com"

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_email" not in session:
            flash("Login required", "error")
            return redirect(url_for("login"))

        if session["user_email"] != ADMIN_EMAIL:
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

if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace(
            "postgres://", "postgresql://", 1
        )
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        "postgresql://chetan-yalij:3151@localhost:5432/ebooklib"
    )

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 300
}

db = SQLAlchemy(app)

# ------------------- Book Model -------------------
class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(50), default="Uncategorized")
    cover_url = db.Column(db.String(500))
    pdf_url = db.Column(db.String(500))

# ------------------- Create Tables -------------------
with app.app_context():
    db.create_all()
    print("✅ Database tables ready")

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

# =================== AUTH ===================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        session["user_email"] = email
        flash(f"Logged in as {email}", "success")
        return redirect(url_for("index"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user_email", None)
    flash("Logged out successfully", "info")
    return redirect(url_for("index"))

# =================== SEARCH ===================

@app.route("/api/suggestions")
def suggestions():
    query = request.args.get("query", "")
    if len(query) < 2:
        return jsonify([])

    results = Book.query.filter(
        (Book.title.ilike(f"%{query}%")) |
        (Book.author.ilike(f"%{query}%"))
    ).limit(5).all()

    return jsonify([
        {
            "title": b.title,
            "author": b.author,
            "url": url_for("search", query=b.title)
        }
        for b in results
    ])

@app.route("/search")
def search():
    query = request.args.get("query", "")
    books = []
    if query:
        books = Book.query.filter(
            (Book.title.ilike(f"%{query}%")) |
            (Book.author.ilike(f"%{query}%"))
        ).all()
    return render_template(
        "search_results.html",
        books=books,
        query=query
    )

# =================== ADMIN ===================

@app.route("/admin")
@admin_required
def admin_dashboard():
    total_books = Book.query.count()
    total_authors = db.session.query(
        Book.author
    ).distinct().count()

    category_stats = db.session.query(
        Book.category,
        func.count(Book.id)
    ).group_by(Book.category).all()

    recent_books = Book.query.order_by(
        Book.id.desc()
    ).limit(5).all()

    return render_template(
        "admin_dashboard.html",
        total_books=total_books,
        total_authors=total_authors,
        category_stats=category_stats,
        recent_books=recent_books
    )

@app.route("/upload", methods=["GET", "POST"])
@admin_required
def upload():
    if request.method == "POST":
        title = request.form["title"]
        author = request.form["author"]
        description = request.form.get("description", "")
        category = request.form.get("category", "Uncategorized")

        if Book.query.filter_by(
            title=title, author=author
        ).first():
            flash("This book already exists!")
            return redirect(url_for("upload"))

        cover_url = None
        cover = request.files.get("cover")
        if cover and cover.filename:
            res = cloudinary.uploader.upload(cover)
            cover_url = res["secure_url"]

        pdf = request.files.get("pdf")
        if not pdf or not pdf.filename:
            flash("PDF file is required!")
            return redirect(url_for("upload"))

        pdf_res = cloudinary.uploader.upload(
            pdf, resource_type="raw"
        )

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

        flash("Book uploaded successfully!")
        return redirect(url_for("index"))

    return render_template("upload.html")

@app.route("/upload_json", methods=["GET", "POST"])
@admin_required
def upload_json():
    if request.method == "POST":
        file = request.files.get("json_file")
        if not file or not file.filename.endswith(".json"):
            flash("Invalid JSON file")
            return redirect(request.url)

        data = json.load(file)
        added = skipped = 0

        for b in data:
            title = b.get("title")
            author = b.get("author")
            if not title or not author:
                continue

            if Book.query.filter_by(
                title=title, author=author
            ).first():
                skipped += 1
                continue

            db.session.add(Book(
                title=title,
                author=author,
                description=b.get("description", ""),
                category=b.get("category", "Uncategorized"),
                cover_url=b.get("cover_url"),
                pdf_url=b.get("pdf_url")
            ))
            added += 1

        db.session.commit()
        flash(f"{added} added, {skipped} skipped")
        return redirect(url_for("index"))

    return render_template("upload.html")

# =================== RUN ===================
if __name__ == "__main__":
    app.run(debug=True)
