import os, hashlib
from flask import Flask, render_template, request, send_from_directory, jsonify
from werkzeug.utils import secure_filename
from models import db, Book
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'epub'}

db.init_app(app)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def placeholder_cover(title):
    h = hex(hash(title) % 0xFFFFFF)[2:].zfill(6)
    return f"https://via.placeholder.com/300x450/{h}/FFFFFF?text={title[0].upper()}"

@app.route('/')
def index():
    books = Book.query.all()
    data = [{
        'id': b.id,
        'title': b.title,
        'author': b.author,
        'description': b.description or '',
        'tags': b.tags or '',
        'cover': b.cover_url or placeholder_cover(b.title),
        'format': os.path.splitext(b.file_path)[1][1:].upper(),
        'downloads': b.download_count
    } for b in books]
    return render_template('index.html', books=data)

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        file = request.files.get('file')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            new_book = Book(
                title=request.form['title'],
                author=request.form['author'],
                description=request.form.get('description'),
                file_path=filename,
                tags=request.form.get('tags'),
                cover_url=request.form.get('cover_url')
            )
            db.session.add(new_book)
            db.session.commit()
            return '<script>alert("Uploaded!");window.location="/"</script>'
    return render_template('upload.html')

@app.route('/search')
def search():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    results = Book.query.filter(
        (Book.title.ilike(f'%{q}%')) |
        (Book.author.ilike(f'%{q}%')) |
        (Book.tags.ilike(f'%{q}%'))
    ).all()
    data = [{
        'id': b.id,
        'title': b.title,
        'author': b.author,
        'description': b.description or '',
        'tags': b.tags or '',
        'cover': b.cover_url or placeholder_cover(b.title),
        'format': os.path.splitext(b.file_path)[1][1:].upper(),
        'downloads': b.download_count
    } for b in results]
    return jsonify(data)

@app.route('/download/<int:book_id>')
def download(book_id):
    book = Book.query.get_or_404(book_id)
    book.download_count += 1
    db.session.commit()
    return send_from_directory(app.config['UPLOAD_FOLDER'], book.file_path)

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)
