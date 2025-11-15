import os
from flask import Flask, render_template, request, redirect
from models import db, Book
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://postgres:password@localhost:5432/ebooklib')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET'),
    secure=True
)

def placeholder_cover(title):
    return f"https://via.placeholder.com/300x450/6366f1/ffffff?text={title[:2].upper()}"

@app.route('/')
def index():
    search = request.args.get('search', '')
    if search:
        books = Book.query.filter(
            Book.title.ilike(f'%{search}%') |
            Book.author.ilike(f'%{search}%') |
            Book.tags.ilike(f'%{search}%')
        ).all()
    else:
        books = Book.query.all()
    return render_template('index.html', books=books)

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        title = request.form['title']
        author = request.form['author']
        description = request.form.get('description', '')
        tags = request.form.get('tags', '')
        cover_url = request.form.get('cover_url') or placeholder_cover(title)

        upload_type = request.form.get('upload_type', 'file')

        if upload_type == 'file':
            file = request.files['file']
            result = cloudinary.uploader.upload(file)
            file_url = result['secure_url']
        else:
            file_url = request.form['book_url']

        book = Book(title=title, author=author, description=description,
                    file_path=file_url, tags=tags, cover_url=cover_url)
        db.session.add(book)
        db.session.commit()
        return '<script>alert("Book Added!"); location="/" </script>'

    return render_template('upload.html')

@app.route('/download/<int:book_id>')
def download(book_id):
    book = Book.query.get_or_404(book_id)
    book.download_count += 1
    db.session.commit()
    return redirect(book.file_path)

# create table first time
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)