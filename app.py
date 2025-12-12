from flask import Flask, render_template, request, redirect, url_for, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

import os
import base64
import requests
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import zipfile
import json

from models import db, User, Record


# -----------------------------
# App Setup
# -----------------------------
app = Flask(__name__)
app.secret_key = "super-secret-key-change-this"

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
db.init_app(app)

UPLOAD_FOLDER = "static/uploads"
TEMP_FOLDER = "static/temp"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TEMP_FOLDER, exist_ok=True)


# -----------------------------
# Login Setup
# -----------------------------
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# -----------------------------
# Vision Model
# -----------------------------
OLLAMA_API = "http://127.0.0.1:11434/api/generate"


def ollama_vision(model, prompt, image_path):
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    payload = {
        "model": model,
        "prompt": prompt,
        "images": [img_b64],
        "stream": False
    }

    try:
        res = requests.post(OLLAMA_API, json=payload, timeout=180)
        return res.json().get("response", "")
    except:
        return "(Error calling model)"


def generate_marketing_texts(path, language):
    prompts = {
        "ecommerce": f"Generate a persuasive e-commerce product description in {language}.",
        "xiaohongshu": f"Generate a Xiaohongshu-style post in {language}.",
        "instagram": f"Generate an Instagram caption with emojis in {language}.",
        "seo": f"Generate an SEO-optimized marketing paragraph in {language}.",
        "bullets": f"List 5 bullet-point features in {language}."
    }

    result = {}
    for k, p in prompts.items():
        result[k] = ollama_vision("llava:7b", p, path)

    return result


# -----------------------------
# AUTH ROUTES
# -----------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])

        if User.query.filter_by(email=email).first():
            return "User already exists."

        user = User(email=email, password=password)
        db.session.add(user)
        db.session.commit()

        return redirect("/login")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect("/")

        return "Incorrect login."

    return render_template("login.html")


@app.route("/logout")
def logout():
    logout_user()
    return redirect("/login")


# -----------------------------
# MAIN PAGE
# -----------------------------
@app.route("/")
@login_required
def index():
    return render_template("index.html")


@app.route("/caption", methods=["POST"])
@login_required
def caption():

    image = request.files["image"]

    filename = datetime.now().strftime("%Y%m%d_%H%M%S_") + image.filename
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    image.save(filepath)

    cap_llava = ollama_vision("llava:7b", "Describe this image.", filepath)
    cap_bak = ollama_vision("bakllava:7b", "Describe this image.", filepath)

    raw_tags = ollama_vision("llava:7b", "5 short tags separated by commas.", filepath)
    tags = [t.strip() for t in raw_tags.split(",")]

    en = generate_marketing_texts(filepath, "English")
    cn = generate_marketing_texts(filepath, "Chinese")
    fr = generate_marketing_texts(filepath, "French")

    rec = Record(
        user_id=current_user.id,
        image_path=filepath,
        caption_llava=cap_llava,
        caption_bak=cap_bak,
        tags=",".join(tags),
        marketing_en=json.dumps(en),
        marketing_cn=json.dumps(cn),
        marketing_fr=json.dumps(fr)
    )
    db.session.add(rec)
    db.session.commit()

    return render_template(
        "result.html",
        image_url=filepath,
        caption_llava=cap_llava,
        caption_bak=cap_bak,
        tags=tags,
        marketing_en=en,
        marketing_cn=cn,
        marketing_fr=fr,
        record_id=rec.id
    )


# -----------------------------
# ASK ABOUT IMAGE
# -----------------------------
@app.route("/ask", methods=["POST"])
@login_required
def ask():

    question = request.form.get("question")
    image_path = request.form.get("image_path")
    record_id = request.form.get("record_id")

    # Stronger prompting
    prompt = f"Answer the question strictly based on the image content:\n{question}"

    answer = ollama_vision("llava:7b", prompt, image_path)

    rec = Record.query.get(record_id)

    return render_template(
        "result.html",
        image_url=image_path,
        caption_llava=rec.caption_llava,
        caption_bak=rec.caption_bak,
        tags=rec.tags.split(","),
        marketing_en=json.loads(rec.marketing_en),
        marketing_cn=json.loads(rec.marketing_cn),
        marketing_fr=json.loads(rec.marketing_fr),
        answer=answer,
        question=question,   # <<< IMPORTANT FIX
        record_id=record_id
    )



# -----------------------------
# HISTORY
# -----------------------------
@app.route("/history")
@login_required
def history():

    records = Record.query.filter_by(user_id=current_user.id).order_by(Record.id.desc()).all()
    return render_template("history.html", records=records)


@app.route("/delete/<int:record_id>", methods=["POST"])
@login_required
def delete_record(record_id):

    rec = Record.query.get(record_id)

    if not rec or rec.user_id != current_user.id:
        return "Not allowed", 403

    try:
        if os.path.exists(rec.image_path):
            os.remove(rec.image_path)
    except:
        pass

    db.session.delete(rec)
    db.session.commit()

    return redirect("/history")


# -----------------------------
# PDF DOWNLOAD
# -----------------------------
@app.route("/download/pdf/<int:record_id>")
@login_required
def download_pdf(record_id):

    rec = Record.query.get(record_id)

    if not rec or rec.user_id != current_user.id:
        return "No permission", 403

    pdf_path = f"{TEMP_FOLDER}/report_{record_id}.pdf"

    c = canvas.Canvas(pdf_path, pagesize=letter)
    width, height = letter

    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, height - 50, "AI Image Caption Report")

    try:
        img = ImageReader(rec.image_path)
        c.drawImage(img, 50, height - 300, width=250, preserveAspectRatio=True)
    except:
        pass

    y = height - 320

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "LLaVA Caption:")
    y -= 15
    c.setFont("Helvetica", 10)

    for line in rec.caption_llava.split("\n"):
        c.drawString(50, y, line)
        y -= 12

    c.setFont("Helvetica-Bold", 12)
    y -= 20
    c.drawString(50, y, "Tags:")
    y -= 15

    for tag in rec.tags.split(","):
        c.drawString(50, y, f"- {tag}")
        y -= 12

    c.save()
    return send_file(pdf_path, as_attachment=True)


# -----------------------------
# ZIP DOWNLOAD
# -----------------------------
@app.route("/download/zip/<int:record_id>")
@login_required
def download_zip(record_id):

    rec = Record.query.get(record_id)

    if not rec or rec.user_id != current_user.id:
        return "Not allowed", 403

    zip_path = f"{TEMP_FOLDER}/record_{record_id}.zip"

    with zipfile.ZipFile(zip_path, "w") as z:

        z.write(rec.image_path, arcname="image.jpg")

        z.writestr("captions.txt",
                   f"LLaVA:\n{rec.caption_llava}\n\nBakLLaVA:\n{rec.caption_bak}")

        z.writestr("tags.txt", rec.tags)

        z.writestr("marketing_en.json", rec.marketing_en)
        z.writestr("marketing_cn.json", rec.marketing_cn)
        z.writestr("marketing_fr.json", rec.marketing_fr)

        z.writestr("meta.json", json.dumps({
            "created_at": rec.created_at.isoformat()
        }, indent=4))

    return send_file(zip_path, as_attachment=True)


# -----------------------------
# RUN
# -----------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
