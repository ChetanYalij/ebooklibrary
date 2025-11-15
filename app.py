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
            if file and allowed_file(file.filename):
                upload_result = cloudinary.uploader.upload(file)
                file_url = upload_result['secure_url']
            else:
                return "Invalid file!", 400
        else:  # URL
            file_url = request.form['book_url']
            if not file_url.startswith(('http://', 'https://')):
                return "Invalid URL!", 400

        new_book = Book(
            title=title,
            author=author,
            description=description,
            file_path=file_url,
            tags=tags,
            cover_url=cover_url
        )
        db.session.add(new_book)
        db.session.commit()

        return '<script>alert("Book Added Successfully!"); window.location="/"</script>'

    return render_template('upload.html')
if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)
