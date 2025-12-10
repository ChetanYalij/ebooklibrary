import os, requests, uuid
from flask import Flask, render_template, request, redirect, session, flash, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader
from datetime import datetime
import cloudinary
import cloudinary.uploader

# =========== APP SETUP ===========
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'super-secret-elibrary-2025')

# =========== DATABASE (Render + Local दोन्ही साठी काम करेल) ===========
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql:///elibrary')  # Render वर DATABASE_URL मिळेल
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
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
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(100), default='Community')
    description = db.Column(db.Text)
    file_path = db.Column(db.String(500), nullable=False)
    cover_url = db.Column(db.String(500))
    tags = db.Column(db.String(200))
    download_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Book {self.title}>"

# =========== PLACEHOLDER COVER ===========
def placeholder_cover(text):
    return f"https://via.placeholder.com/300x450/6366f1/ffffff?text={text[:2].upper()}"

# =========== HOME ===========
@app.route('/')
def index():
    search = request.args.get('search', '').strip()
    query = Book.query.order_by(Book.created_at.desc())

    if search:
        query = query.filter(
            db.or_(
                Book.title.ilike(f'%{search}%'),
                Book.author.ilike(f'%{search}%'),
                Book.tags.ilike(f'%{search}%')
            )
        )
    books = query.all()
    return render_template('index.html', books=books, user=session.get('user'))

# =========== ADD FROM URL (सर्वात महत्त्वाचं!) ===========
@app.route('/add-from-url', methods=['GET', 'POST'])
def add_from_url():
    if request.method == 'POST':
        pdf_url = request.form['pdf_url'].strip()
        title = request.form.get('title', '').strip()

        if not pdf_url.lower().endswith('.pdf'):
            flash('PDF लिंक असली पाहिजे (.pdf)', 'error')
            return redirect(request.url)

        try:
            # डाउनलोड कर
            headers = {'User-Agent': 'Mozilla/5.0'}
            r = requests.get(pdf_url, headers=headers, stream=True, timeout=30)
            r.raise_for_status()

            temp_path = f"temp_{uuid.uuid4().hex}.pdf"
            with open(temp_path, 'wb') as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)

            # टायटल काढ
            if not title:
                try:
                    reader = PdfReader(temp_path)
                    title = reader.metadata.title or "Unknown Book"
                except:
                    title = "Unknown Book"

            # Cloudinary वर अपलोड
            upload_result = cloudinary.uploader.upload(
                temp_path,
                folder="elibrary/pdfs",
                resource_type="raw"
            )
            pdf_url_cloud = upload_result['secure_url']

            # कव्हर
            cover = placeholder_cover(title)

            # डेटाबेसमध्ये सेव्ह कर
            new_book = Book(
                title=title,
                author="Community",
                file_path=pdf_url_cloud,
                cover_url=cover
            )
            db.session.add(new_book)
            db.session.commit()

            os.remove(temp_path)  # टेम्प फाइल डिलीट
            flash(f'"{title}" यशस्वीरीत्या जोडले!', 'success')
            return redirect('/')

        except Exception as e:
            flash('काहीतरी चुकलं. लिंक सार्वजनिक असली पाहिजे.', 'error')

    return render_template('add_from_url.html')

# =========== DOWNLOAD ===========
@app.route('/download/<int:book_id>')
def download(book_id):
    book = Book.query.get_or_404(book_id)
    book.download_count += 1
    db.session.commit()
    return redirect(book.file_path)

# =========== LOGIN PAGE (साधी) ===========
@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

# =========== CREATE TABLES ===========
with app.app_context():
    db.create_all()

# =========== RUN ===========
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)