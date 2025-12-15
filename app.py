import os
import json
from flask import Flask, render_template, request, flash, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import cloudinary
import cloudinary.uploader

# ------------------- Flask App Setup -------------------
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-fallback-secret-key-change-this')

# ------------------- Cloudinary Config -------------------
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)

# ------------------- Database Config (Important for Render!) -------------------
database_url = os.getenv('DATABASE_URL')

if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
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
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(50), default='Uncategorized')
    cover_url = db.Column(db.String(500), nullable=True)
    pdf_url = db.Column(db.String(500), nullable=True)

    def __repr__(self):
        return f"<Book {self.title}>"

# ------------------- Create Tables (safe method) -------------------
# Do not put db.create_all() at the end of the file or at import time!
# Run in app context
@app.before_first_request
def create_tables():
    db.create_all()
    print("Database tables created successfully!")

# ------------------- Routes -------------------

@app.route('/')
def index():
    books = Book.query.all()
    return render_template('index.html', books=books)

# Single book upload
@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        title = request.form['title']
        author = request.form['author']
        description = request.form.get('description', '')
        category = request.form.get('category', 'Uncategorized')

        # Duplicate Check
        if Book.query.filter_by(title=title, author=author).first():
            flash('This book is already in the database!')
            return redirect(url_for('upload'))

        cover_url = None
        pdf_url = None

        # Upload cover
        if 'cover' in request.files:
            cover_file = request.files['cover']
            if cover_file.filename != '':
                cover_upload = cloudinary.uploader.upload(cover_file)
                cover_url = cover_upload['secure_url']

        # Upload PDF
        if 'pdf' in request.files:
            pdf_file = request.files['pdf']
            if pdf_file.filename != '':
                pdf_upload = cloudinary.uploader.upload(pdf_file, resource_type="raw")
                pdf_url = pdf_upload['secure_url']
            else:
                flash('PDF file required!')
                return redirect(url_for('upload'))

        # Save new book
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

# Upload multiple books with JSON
@app.route('/upload_json', methods=['GET', 'POST'])
def upload_json():
    if request.method == 'POST':
        if 'json_file' not in request.files:
            flash('JSON file not selected!')
            return redirect(request.url)

        file = request.files['json_file']
        if file.filename == '' or not file.filename.lower().endswith('.json'):
            flash('Please select a valid .json file!')
            return redirect(request.url)

        try:
            data = json.load(file)
            if not isinstance(data, list):
                flash('JSON should contain a list of books (array)!')
                return redirect(request.url)

            added_count = 0
            skipped_count = 0

            for book_data in data:
                title = book_data.get('title')
                author = book_data.get('author')
                if not title or not author:
                    continue

                if Book.query.filter_by(title=title, author=author).first():
                    skipped_count += 1
                    continue

                new_book = Book(
                    title=title,
                    author=author,
                    description=book_data.get('description', ''),
                    category=book_data.get('category', 'Uncategorized'),
                    cover_url=book_data.get('cover_url'),
                    pdf_url=book_data.get('pdf_url')
                )
                db.session.add(new_book)
                added_count += 1

            db.session.commit()
            flash(f'Success! {added_count} new books added. {skipped_count} already existed so skipped.')
        except json.JSONDecodeError:
            flash('The JSON file is in the wrong format.!')
        except Exception as e:
            flash(f'error: {str(e)}')

        return redirect(url_for('index'))

    return render_template('upload_json.html')

if __name__ == '__main__':
    app.run(debug=True)