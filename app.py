import os
import json
from flask import Flask, render_template, request, flash, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

# ------------------- Load .env (local only) -------------------
load_dotenv()

# ------------------- Flask App Setup -------------------
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'change-this-secret-key')

# ------------------- Cloudinary Config -------------------
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)

# ------------------- Database Config (Render + Local) -------------------
DATABASE_URL = os.getenv('DATABASE_URL')

if DATABASE_URL:
    # Render PostgreSQL fix
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://chetan-yalij:3151@localhost:5432/ebooklib'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300
}

db = SQLAlchemy(app)

# ------------------- Book Model -------------------
class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(50), default='Uncategorized')
    cover_url = db.Column(db.String(500))
    pdf_url = db.Column(db.String(500))

    def __repr__(self):
        return f"<Book {self.title}>"

# ------------------- Create Tables (SAFE) -------------------
with app.app_context():
    db.create_all()
    print("✅ Database tables ready")

# ------------------- Routes -------------------

@app.route('/')
def index():
    books = Book.query.all()
    return render_template('index.html', books=books)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

# ------------------- Upload Single Book -------------------
@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        title = request.form['title']
        author = request.form['author']
        description = request.form.get('description', '')
        category = request.form.get('category', 'Uncategorized')

        # Duplicate check
        if Book.query.filter_by(title=title, author=author).first():
            flash('This book already exists!')
            return redirect(url_for('upload'))

        cover_url = None
        pdf_url = None

        # Upload cover
        cover_file = request.files.get('cover')
        if cover_file and cover_file.filename:
            cover_upload = cloudinary.uploader.upload(cover_file)
            cover_url = cover_upload.get('secure_url')

        # Upload PDF
        pdf_file = request.files.get('pdf')
        if not pdf_file or not pdf_file.filename:
            flash('PDF file is required!')
            return redirect(url_for('upload'))

        pdf_upload = cloudinary.uploader.upload(
            pdf_file, resource_type="raw"
        )
        pdf_url = pdf_upload.get('secure_url')

        # Save book
        new_book = Book(
            title=title,
            author=author,
            description=description,
            category=category,
            cover_url=cover_url,
            pdf_url=pdf_url
        )

        db.session.add(new_book)
        db.session.commit()

        flash('Book uploaded successfully!')
        return redirect(url_for('index'))

    return render_template('upload.html')

# ------------------- Upload Multiple Books via JSON -------------------
@app.route('/upload_json', methods=['GET', 'POST'])
def upload_json():
    if request.method == 'POST':
        file = request.files.get('json_file')

        if not file or not file.filename.endswith('.json'):
            flash('Please upload a valid JSON file!')
            return redirect(request.url)

        try:
            data = json.load(file)
            if not isinstance(data, list):
                flash('JSON must contain a list of books!')
                return redirect(request.url)

            added = 0
            skipped = 0

            for book in data:
                title = book.get('title')
                author = book.get('author')

                if not title or not author:
                    continue

                if Book.query.filter_by(title=title, author=author).first():
                    skipped += 1
                    continue

                db.session.add(Book(
                    title=title,
                    author=author,
                    description=book.get('description', ''),
                    category=book.get('category', 'Uncategorized'),
                    cover_url=book.get('cover_url'),
                    pdf_url=book.get('pdf_url')
                ))
                added += 1

            db.session.commit()
            flash(f"{added} books added, {skipped} skipped (duplicates)")

        except Exception as e:
            flash(f"Error: {str(e)}")

        return redirect(url_for('index'))

    return render_template('upload.html')

# ------------------- Run App -------------------
if __name__ == '__main__':
    app.run(debug=True)
