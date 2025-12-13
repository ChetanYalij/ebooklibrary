import os, requests, uuid
from flask import Flask, render_template, request, redirect, flash, url_for, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader
from datetime import datetime

# =========== APP SETUP ===========
app = Flask(__name__)
app.secret_key = 'super-secret-elibrary-2025'

# =========== DATABASE - तुझ्या लॅपटॉपवर PostgreSQL ===========
# तुझा पासवर्ड बदला जर वेगळा असेल
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:npg_pI3ObLUGiFs8@localhost/ebooklibrary'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# =========== पुस्तकं तुझ्या लॅपटॉपवर सेव्ह होतील ===========
BOOKS_FOLDER = os.path.join('static', 'books')
os.makedirs(BOOKS_FOLDER, exist_ok=True)
app.config['BOOKS_FOLDER'] = BOOKS_FOLDER

# =========== BOOK MODEL ===========
class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    author = db.Column(db.String(200), default='Community')
    filename = db.Column(db.String(300), nullable=False)  # PDF फाइल नाव
    cover_url = db.Column(db.String(500), default='https://via.placeholder.com/300x450/6366f1/ffffff?text=Book')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Book {self.title}>"

# =========== PLACEHOLDER COVER ===========
def placeholder_cover(text):
    return f"https://via.placeholder.com/300x450/6366f1/ffffff?text={text[:2].upper()}"

# =========== HOME PAGE ===========
@app.route('/')
def index():
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
    return render_template('index.html', books=books, search=search)

# =========== ADD FROM URL ===========
@app.route('/add-from-url', methods=['GET', 'POST'])
def add_from_url():
    if request.method == 'POST':
        pdf_url = request.form['pdf_url'].strip()
        title = request.form.get('title', '').strip()

        if not pdf_url.lower().endswith('.pdf'):
            flash('फक्त PDF लिंक द्या (.pdf)', 'error')
            return redirect(request.url)

        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            r = requests.get(pdf_url, headers=headers, stream=True, timeout=30)
            r.raise_for_status()

            # युनिक फाइल नाव
            filename = secure_filename(f"{uuid.uuid4().hex}.pdf")
            file_path = os.path.join(app.config['BOOKS_FOLDER'], filename)

            with open(file_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            # टायटल ऑटो काढ
            if not title:
                try:
                    reader = PdfReader(file_path)
                    metadata = reader.metadata
                    title = metadata.title if metadata and metadata.title else "अज्ञात पुस्तक"
                except:
                    title = "अज्ञात पुस्तक"

            # डेटाबेसमध्ये सेव्ह कर
            new_book = Book(
                title=title.strip() or "अज्ञात पुस्तक",
                author="Community",
                filename=filename
            )
            db.session.add(new_book)
            db.session.commit()

            flash(f'"{title}" यशस्वीरीत्या जोडले!', 'success')
            return redirect('/')

        except requests.exceptions.RequestException as e:
            flash(f'डाउनलोड त्रुटी: {str(e)}. लिंक सार्वजनिक असली पाहिजे.', 'error')
        except Exception as e:
            flash(f'अज्ञात त्रुटी: {str(e)}', 'error')

    return render_template('add_from_url.html')

# =========== READ BOOK ===========
@app.route('/read/<filename>')
def read_book(filename):
    try:
        return send_from_directory(app.config['BOOKS_FOLDER'], filename)
    except:
        flash('पुस्तक सापडले नाही!', 'error')
        return redirect('/')

# =========== CREATE TABLES ===========
with app.app_context():
    db.create_all()
    print("Tables created successfully!")

# =========== RUN APP ===========
if __name__ == '__main__':
    app.run(debug=True)