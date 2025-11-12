from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    file_path = db.Column(db.String(200), nullable=False)
    tags = db.Column(db.String(200))
    cover_url = db.Column(db.String(300))
    download_count = db.Column(db.Integer, default=0)
