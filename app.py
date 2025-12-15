import os, requests, uuid, json
from flask import Flask, render_template, request, redirect, flash, url_for, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader
from datetime import datetime

# =========== APP SETUP ===========
app = Flask(__name__)
app.secret_key = 'super-secret-elibrary-2025'

# =========== DATABASE ===========
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:npg_pI3ObLUGiFs8@localhost/ebooklibrary'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# =========== STORAGE ===========
BOOKS_FOLDER = os.path.join('static', 'books')
os.makedirs(BOOKS_FOLDER, exist_ok=True)
app.config['BOOKS_FOLDER'] = BOOKS_FOLDER

# =========== BOOK MODEL ===========
class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    author = db.Column(db.String(200), default='Community')
    filename = db.Column(db.String(300), nullable=False)
    cover_url = db.Column(db.String(500), default='https://via.placeholder.com/300x450/6366f1/ffffff?text=Book')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# =========== HOME ===========
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

# =====================================================
# ✅ SINGLE BOOK UPLOAD
# =====================================================
@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        title = request.form['title'].strip()
        author = request.form['author'].strip()

        if not title or not author:
            flash('Title आणि Author आवश्यक आहेत!')
            return redirect(request.url)

        if Book.query.filter_by(title=title, author=author).first():
            flash('हे पुस्तक आधीच आहे!')
            return redirect(request.url)

        # PDF Upload
        pdf = request.files.get('pdf')
        if not pdf or pdf.filename == '':
            flash('PDF फाइल आवश्यक आहे!')
            return redirect(request.url)

        filename = secure_filename(f"{uuid.uuid4().hex}.pdf")
        pdf.save(os.path.join(app.config['BOOKS_FOLDER'], filename))

        new_book = Book(
            title=title,
            author=author,
            filename=filename
        )

        db.session.add(new_book)
        db.session.commit()

        flash('पुस्तक यशस्वी अपलोड झाले!')
        return redirect(url_for('index'))

    return render_template('upload.html')

# =====================================================
# ✅ JSON MULTIPLE BOOK UPLOAD
# =====================================================
@app.route('/upload_json', methods=['GET', 'POST'])
def upload_json():
    if request.method == 'POST':
        file = request.files.get('json_file')

        if not file or not file.filename.endswith('.json'):
            flash('कृपया वैध JSON फाइल निवडा!')
            return redirect(request.url)

        try:
            data = json.load(file)
            if not isinstance(data, list):
                flash('JSON मध्ये array असावा!')
                return redirect(request.url)

            added, skipped = 0, 0

            for item in data:
                title = item.get('title')
                author = item.get('author', 'Community')
                pdf_url = item.get('pdf_url')

                if not title or not pdf_url:
                    skipped += 1
                    continue

                if Book.query.filter_by(title=title, author=author).first():
                    skipped += 1
                    continue

                # PDF download
                r = requests.get(pdf_url, stream=True, timeout=30)
                r.raise_for_status()

                filename = secure_filename(f"{uuid.uuid4().hex}.pdf")
                path = os.path.join(app.config['BOOKS_FOLDER'], filename)

                with open(path, 'wb') as f:
                    for chunk in r.iter_content(8192):
                        f.write(chunk)

                book = Book(
                    title=title,
                    author=author,
                    filename=filename,
                    cover_url=item.get('cover_url', Book.cover_url.default.arg)
                )
                db.session.add(book)
                added += 1

            db.session.commit()
            flash(f'यशस्वी! {added} पुस्तके जोडली, {skipped} स्किप.')

        except Exception as e:
            flash(f'त्रुटी: {str(e)}')

        return redirect(url_for('index'))

    return render_template('upload_json.html')

# =========== READ BOOK ===========
@app.route('/read/<filename>')
def read_book(filename):
    return send_from_directory(app.config['BOOKS_FOLDER'], filename)

# =========== INIT DB ===========
with app.app_context():
    db.create_all()

# =========== RUN ===========
if __name__ == '__main__':
    app.run(debug=True)
