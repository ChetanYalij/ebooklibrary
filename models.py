# models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Book(db.Model):
    __tablename__ = 'books'          

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String(500), nullable=False)
    author = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, nullable=True)
    file_path = db.Column(db.Text, nullable=False)      
    cover_url = db.Column(db.Text, nullable=True)         
    tags = db.Column(db.String(500), nullable=True)       
    download_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Book {self.title}>"