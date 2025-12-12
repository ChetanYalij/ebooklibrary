import os, requests, uuid
from flask import Flask, render_template, request, redirect, session, flash, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine, or_
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader
from datetime import datetime
import cloudinary
import cloudinary.uploader

# =========== APP SETUP ===========
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'super-secret-elibrary-2025')

# =========== DATABASE (Render + Supabase + Local) - FULL FIX ===========
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql:///elibrary')  # Local fallback
if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

# Engine with better pool settings (e3q8 error fix)
engine = create_engine(
    DATABASE_URL,
    pool_size=10,        
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=3600,
    pool_pre_ping=True
)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_size': 10,
    'max_overflow': 20,
    'pool_timeout': 30,
    'pool_recycle': 3600
}
db = SQLAlchemy(app)

# =========== CLOUDINARY ===========
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET'),
    secure=True
)

# =========== BOOK MODEL ===========
class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.Text, nullable=False)
    author = db.Column(db.Text, default='Community')
    file_path = db.Column(db.Text, nullable=False)
    cover_url = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Book {self.title}>"

# =========== PLACEHOLDER COVER ===========
def placeholder_cover(text):
    return f"https://via.placeholder.com/300x450/6366f1/ffffff?text={text[:2].upper()}"

# =========== HOME ===========
@app.route('/')
def index():
    try:
        with db.session.begin():
            search = request.args.get('search', '').strip()
            query = Book.query.order_by(Book.created_at.desc())
            if search:
                query = query.filter(
                    or_(
                        Book.title.ilike(f'%{search}%'),
                        Book.author.ilike(f'%{search}%')
                    )
                )
            books = query.all()

        return render_template('index.html', books=books)

    except Exception as e:
        db.session.rollback()
        flash(f'Database error: {str(e)}', 'error')
        return render_template('index.html', books=[])

# =========== ADD FROM URL  ===========
@app.route('/add-from-url', methods=['GET', 'POST'])
def add_from_url():
    if request.method == 'POST':
        
        pdf_url = request.form['pdf_url'].strip()
        title = request.form.get('title', '').strip()

        if not pdf_url.lower().endswith('.pdf'):
            flash('There should be a PDF link (.pdf)', 'error')
            return redirect(request.url)

        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            r = requests.get(pdf_url, headers=headers, stream=True, timeout=30, allow_redirects=True)
            r.raise_for_status()

            temp_path = f"temp_{uuid.uuid4().hex}.pdf"
            with open(temp_path, 'wb') as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)

            if not title:
                try:
                    reader = PdfReader(temp_path)
                    title = reader.metadata.title or "Unknown Book"
                except:
                    title = "Unknown Book"

            # Upload Cloudinary
            upload_result = cloudinary.uploader.upload(
                temp_path,
                folder="elibrary/pdfs",
                resource_type="raw"
            )
            pdf_url_cloud = upload_result['secure_url']
            cover = placeholder_cover(title)

            new_book = Book(
                title=title,
                author="Community",
                file_path=pdf_url_cloud,
                cover_url=cover
            )
            db.session.add(new_book)
            db.session.commit()
            os.remove(temp_path)

        flash(f'"{title}" Added successfully!', 'success')
        return redirect('/')

    except Exception as e:
        if os.path.exists(temp_path):
            try:
               os.remove(temp_path)
            except:
                pass
            flash(f'Error: {str(e)}. Link must be public.', 'error')
            return redirect(request.url)

    return render_template('add_from_url.html')

# =========== DOWNLOAD ===========
@app.route('/download/<int:book_id>')
def download(book_id):
    book = Book.query.get_or_404(book_id)
    return redirect(book.file_path)

# =========== LOGIN ===========
@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

# =========== CREATE TABLES (secure) ===========
with app.app_context():
    db.create_all()
    print("Tables created successfully!")

# =========== RUN (Render) ===========
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)