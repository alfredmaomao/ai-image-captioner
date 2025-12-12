from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True)
    password = db.Column(db.String(120))

class Record(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    image_path = db.Column(db.String(300))
    caption_llava = db.Column(db.Text)
    caption_bak = db.Column(db.Text)
    tags = db.Column(db.Text)

    marketing_en = db.Column(db.Text)
    marketing_cn = db.Column(db.Text)
    marketing_fr = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
