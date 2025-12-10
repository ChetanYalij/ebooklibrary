import os, requests, uuid
from flask import Flask, render_template, request, redirect, session, jsonify, url_for, flash
from models import db, Book
from sqlalchemy import or_
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader
from datetime import datetime
import cloudinary
import cloudinary.uploader
import firebase_admin
from firebase_admin import auth, credentials

# ============  LOAD ENV  =============
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'super-secret-key-for-elibraryrary-2025')


# ==============  DATABASE CONFIG  =================

database_url = os.getenv('DATABASE_URL')
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql+psycopg2://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql:///elibrary'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)


# ==============   CLOUDINARY CONFIG   ================
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET'),
    secure=True
)


# ===============   FIREBASE ADMIN   ===============
if not firebase_admin._apps:
    try:
        private_key = os.getenv("FIREBASE_PRIVATE_KEY")
        if private_key:
            private_key = private_key.replace('\\n', '\n')
        else:
            print("NO FIREBASE_PRIVATE_KEY")
            private_key = "dummy-key-for-local-testing"

        cred = credentials.Certificate({
            "type": "service_account",
            "project_id": os.getenv("FIREBASE_PROJECT_ID", "elibraryrary"),
            "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID"),
            "private_key": private_key,
            "client_email": os.getenv("FIREBASE_CLIENT_EMAIL"),
            "client_id": os.getenv("FIREBASE_CLIENT_ID"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": os.getenv("FIREBASE_CLIENT_CERT_URL")
        })
        firebase_admin.initialize_app(cred)
        print("Firebase Admin connect successful!")
    except Exception as e:
        print("Skip Firebase (local testing):", e)
        pass


# ================   PLACEHOLDER COVER   =================
def placeholder_cover(title):
    return f"https://via.placeholder.com/300x450/6366f1/ffffff?text={title[:2].upper()}"


# ================   HOME PAGE   ================

@app.route('/')
def index():
    search = request.args.get('search', '').strip()
    query = Book.query.order_by(Book.created_at.desc())

    if search:
        query = query.filter(
            or_(
                Book.title.ilike(f'%{search}%'),
                Book.author.ilike(f'%{search}%'),
                Book.tags.ilike(f'%{search}%')
            )
        )

    books = query.all()
    books_list = [
        {
            'id': b.id,
            'title': b.title,
            'author': b.author,
            'description': b.description or '',
            'file_path': b.file_path,
            'cover_url': b.cover_url or placeholder_cover(b.title),
            'tags': b.tags or '',
            'download_count': b.download_count or 0
        } for b in books
    ]

    return render_template('index.html', books=books_list, user=session.get('user'))


# ============   UPLOAD BOOK (CLOUDINARY OR URL)   ==================
@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if not session.get('user'):
        return redirect('/login')

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
            file_url = request.form.get('book_url')
            if not file_url:
                return "URL is required!", 400

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
        return '<script>alert("Book uploaded successfully!"); window.location="/"</script>'

    return render_template('upload.html', user=session.get('user'))


# =============   DOWNLOAD BOOK    =================
@app.route('/download/<int:book_id>')
def download(book_id):
    book = Book.query.get_or_404(book_id)
    book.download_count = (book.download_count or 0) + 1
    db.session.commit()
    return redirect(book.file_path)


# =========================================
# LOGIN WITH FIREBASE
# =========================================
@app.route('/firebase_login', methods=['POST'])
def firebase_login():
    token = request.json.get('token')
    try:
        decoded_token = auth.verify_id_token(token)
        session['user'] = {
            'name': decoded_token.get('name'),
            'email': decoded_token.get('email'),
            'picture': decoded_token.get('picture')
        }
        return jsonify(success=True)
    except Exception as e:
        print("Firebase error:", e)
        return jsonify(success=False), 401


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

@app.route('/login')
def login_page():
    return render_template('login.html')


# ===========   ADD BOOK FROM DIRECT PDF URL   ===========
@app.route('/add-from-url', methods=['GET', 'POST'])
def add_from_url():
    if not session.get('user'):
        return redirect('/login')

    if request.method == 'POST':
        pdf_url = request.form['pdf_url'].strip()
        title = request.form.get('title', '').strip()

        if not pdf_url.lower().endswith('.pdf'):
            flash("Please provide a direct .pdf link!", "error")
            return redirect(request.url)

        # ====== DOWNLOAD TEMPORARY PDF ======
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            r = requests.get(pdf_url, headers=headers, timeout=25, stream=True)
            r.raise_for_status()

            os.makedirs("temp", exist_ok=True)
            temp_name = secure_filename(f"{uuid.uuid4().hex}.pdf")
            temp_path = os.path.join("temp", temp_name)

            with open(temp_path, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)

        except Exception as e:
            print("PDF download error:", e)
            flash("Could not download PDF. Link must be public!", "error")
            return redirect(request.url)

        # ====== AUTO TITLE ======
        if not title:
            try:
                reader = PdfReader(temp_path)
                title = reader.metadata.title or "Untitled Book"
            except:
                title = "Unknown Title"

        # ====== UPLOAD TO CLOUDINARY ======
        try:
            upload_result = cloudinary.uploader.upload(
                temp_path,
                folder="elibraryrary/pdfs",
                resource_type="raw"
            )
            cloud_pdf_url = upload_result["secure_url"]
        except Exception as e:
            print("Cloudinary Error:", e)
            flash("Cloudinary upload failed!", "error")
            return redirect(request.url)

        # remove temp file
        try:
            os.remove(temp_path)
        except:
            pass

        # ====== COVER (placeholder only) ======
        cover_url = placeholder_cover(title)

        # ====== SAVE DB ======
        new_book = Book(
            title=title,
            author="Community",
            description="",
            tags="",
            file_path=cloud_pdf_url,
            cover_url=cover_url
        )
        db.session.add(new_book)
        db.session.commit()

        flash(f"{title} added successfully!", "success")
        return redirect('/')

    return render_template('add_from_url.html', user=session.get('user'))


# ============   CREATE TABLES   =============
with app.app_context():
    db.create_all()


# ===========   RUN APP    ================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)