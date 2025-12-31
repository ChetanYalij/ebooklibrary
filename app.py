import os
from functools import wraps
from flask import (
    Flask, render_template, request, session,
    flash, redirect, url_for, jsonify, abort
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from werkzeug.security import generate_password_hash, check_password_hash
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

# ================== DATABASE ==================
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
if DATABASE_URL and "sslmode" not in DATABASE_URL:
    DATABASE_URL += "?sslmode=require"
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
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

class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(50))
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
            flash("Please login first", "error")
            return redirect(url_for("login"))
        user = User.query.get(session["user_id"])
        if not user or not user.is_admin:
            abort(403)  # Forbidden
        return f(*args, **kwargs)
    return wrap

# ================== INIT DB + ADMIN ==================
with app.app_context():
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

# =====================================================
# ================== PUBLIC ROUTES ====================
# =====================================================
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

@app.route("/search")
def search():
    query = request.args.get("query", "").strip()
    books = []
    if query:
        books = Book.query.filter(
            Book.title.ilike(f"%{query}%") |
            Book.author.ilike(f"%{query}%")
        ).all()
    return render_template("search_results.html", books=books, query=query)

@app.route("/download/<int:book_id>")
@login_required
def download_book(book_id):
    book = Book.query.get_or_404(book_id)
    return redirect(book.pdf_url)

# =====================================================
# ================== AUTH ROUTES ======================
# =====================================================
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
            flash("Login successful!", "success")
            return redirect(url_for("admin_dashboard") if user.is_admin else url_for("index"))
        flash("Invalid email or password", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully", "success")
    return redirect(url_for("index"))

# =====================================================
# ================== ADMIN ROUTES =====================
# =====================================================
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

@app.route("/admin/upload", methods=["GET", "POST"])
@admin_required
def upload_book():
    if request.method == "POST":
        cover_url = None
        if request.files.get("cover"):
            cover = cloudinary.uploader.upload(request.files["cover"])
            cover_url = cover["secure_url"]
        pdf = cloudinary.uploader.upload(
            request.files["pdf"], resource_type="raw"
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

# =====================================================
# ================== API ROUTES =======================
# =====================================================
@app.route("/api/books")
def api_books():
    books = Book.query.all()
    return jsonify([
        {
            "id": b.id,
            "title": b.title,
            "author": b.author,
            "category": b.category
        } for b in books
    ])

# ================== ERROR HANDLERS (NO TEMPLATE NEEDED) ==================
@app.errorhandler(403)
def forbidden(e):
    return '''
    <!DOCTYPE html>
    <html lang="mr">
    <head>
        <meta charset="UTF-8">
        <title>प्रवेश नाकारला - ४०३</title>
        <style>
            body {font-family: Arial, sans-serif; background: #f8d7da; color: #721c24; text-align: center; padding: 100px;}
            h1 {font-size: 80px; margin: 0;}
            p {font-size: 22px;}
            a {color: #721c24; text-decoration: underline;}
        </style>
    </head>
    <body>
        <h1>४०३</h1>
        <p>प्रवेश नाकारला गेला.</p>
        <p>तुम्हाला हे पेज पाहण्याची परवानगी नाही. कृपया <a href="/login">लॉगिन</a> करा.</p>
        <p><a href="/">मुख्य पृष्ठावर परत जा</a></p>
    </body>
    </html>
    ''', 403

@app.errorhandler(404)
def not_found(e):
    return '''
    <!DOCTYPE html>
    <html lang="mr">
    <head>
        <meta charset="UTF-8">
        <title>पेज सापडले नाही - ४०४</title>
        <style>
            body {
                font-family: 'Segoe UI', Arial, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                text-align: center;
                padding: 100px 20px;
                margin: 0;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .container {
                max-width: 600px;
                background: rgba(255,255,255,0.15);
                padding: 50px;
                border-radius: 20px;
                backdrop-filter: blur(10px);
                box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            }
            h1 {font-size: 90px; margin: 0; text-shadow: 3px 3px 15px rgba(0,0,0,0.4);}
            p {font-size: 22px; margin: 25px 0;}
            a {
                display: inline-block;
                margin-top: 20px;
                padding: 14px 35px;
                background: white;
                color: #667eea;
                text-decoration: none;
                border-radius: 50px;
                font-weight: bold;
                font-size: 18px;
                transition: all 0.3s;
            }
            a:hover {background: #f0f0f0; transform: translateY(-3px);}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>४०४</h1>
            <p>क्षमस्व, तुम्ही शोधत असलेलं पेज सापडले नाही.</p>
            <p>Sorry, the page you were looking for was not found.</p>
            <p>The URL may be incorrect or the page may have been deleted.</p>
            <a href="/">मुख्य पृष्ठावर परत जा / Return to main page</a>
        </div>
    </body>
    </html>
    ''', 404

# ================== RUN ==================
if __name__ == "__main__":
    app.run(debug=True)