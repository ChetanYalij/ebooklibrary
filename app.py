import os
from flask import Flask, render_template, request, redirect
from models import db, Book
from sqlalchemy import func  # ← योग्य इम्पोर्ट (db_func नव्हे)
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader

load_dotenv()

app = Flask(__name__)

# ========= DATABASE CONFIG =========
database_url = os.getenv('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg2://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///ebooklib.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
    'pool_timeout': 60
}
db.init_app(app)

# ========= CLOUDINARY =========
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET'),
    secure=True
)

def placeholder_cover(title):
    return f"https://via.placeholder.com/300x450/6366f1/ffffff?text={title[:2].upper()}"

# ========= ROUTES =========
@app.route('/')
def index():
    search = request.args.get('search', '').strip()

    if search:
        # योग्य func वापरलं + search.lower() केलं
        books = Book.query.filter(
            func.lower(Book.title).ilike(f'%{search.lower()}%') |
            func.lower(Book.author).ilike(f'%{search.lower()}%') |
            func.lower(Book.tags).ilike(f'%{search.lower()}%')
        ).all()
    else:
        books = Book.query.all()

    books_list = []
    for b in books:
        books_list.append({
            'id': b.id,
            'title': b.title,
            'author': b.author,
            'description': b.description or '',
            'file_path': b.file_path,
            'cover_url': b.cover_url or placeholder_cover(b.title),
            'tags': b.tags or '',
            'download_count': b.download_count or 0
        })

    return render_template('index.html', books=books_list)


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        title = request.form['title'].strip()
        author = request.form['author'].strip()
        description = request.form.get('description', '').strip()
        tags = request.form.get('tags', '').strip()
        cover_url = request.form.get('cover_url') or placeholder_cover(title)
        upload_type = request.form.get('upload_type', 'file')

        if upload_type == 'file':
            file = request.files.get('file')
            if not file or file.filename == '':
                return "No file selected!", 400
            result = cloudinary.uploader.upload(file, resource_type="auto")
            file_url = result['secure_url']
        else:
            # ही चूक होती → "book book_url" → "book_url"
            file_url = request.form.get('book_url')
            if not file_url:
                return "URL is required!", 400

        new_book = Book(title=title, author=author, description=description,
                        file_path=file_url, tags=tags, cover_url=cover_url)
        db.session.add(new_book)
        db.session.commit()
        return '<script>alert("Book Added Successfully!"); window.location="/"</script>'

    return render_template('upload.html')


@app.route('/download/<int:book_id>')
def download(book_id):
    book = Book.query.get_or_404(book_id)
    book.download_count = (book.download_count or 0) + 1
    db.session.commit()
    return redirect(book.file_path)


# ========= CREATE TABLES =========
with app.app_context():
    db.create_all()


# ========= RUN APP =========
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)