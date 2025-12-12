from flask import Flask, render_template, request, send_file
import os
import base64
import requests
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import zipfile
import json

app = Flask(__name__)
UPLOAD_FOLDER = "static/uploads"
TEMP_FOLDER = "static/temp"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TEMP_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

OLLAMA_API = "http://127.0.0.1:11434/api/generate"


# ------------------------------
# Vision request helper
# ------------------------------
def ollama_vision(model, prompt, image_path):
    """Send image + prompt to Ollama Vision model"""
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    payload = {
        "model": model,
        "prompt": prompt,
        "images": [img_b64],
        "stream": False
    }

    res = requests.post(OLLAMA_API, json=payload, timeout=180)
    try:
        return res.json().get("response", "").strip()
    except:
        return "(Error parsing response)"


# ------------------------------
# Generate 5 types of marketing texts
# ------------------------------
def generate_marketing_texts(image_path, language="English"):

    prompts = {
        "ecommerce": f"Generate a persuasive e-commerce product description in {language}.",
        "xiaohongshu": f"Generate a Xiaohongshu lifestyle post in {language}.",
        "instagram": f"Generate a stylish Instagram caption in {language}.",
        "seo": f"Write an SEO-optimized marketing paragraph in {language}.",
        "bullets": f"List 5 bullet-point features in {language}."
    }

    results = {}
    for key, prompt in prompts.items():
        results[key] = ollama_vision("llava:7b", prompt, image_path)

    return results


# ------------------------------
# Routes
# ------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/caption", methods=["POST"])
def caption():

    image = request.files["image"]

    # Save image
    filename = datetime.now().strftime("%Y%m%d_%H%M%S_") + image.filename
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    image.save(filepath)

    # Captions
    caption_llava = ollama_vision("llava:7b", "Describe this image clearly.", filepath)
    caption_bak = ollama_vision("bakllava:7b", "Describe this image clearly.", filepath)

    # Tags
    raw_tags = ollama_vision("llava:7b", "Generate 5 short keyword tags separated by commas.", filepath)
    tags = [t.strip() for t in raw_tags.split(",")]

    # Marketing copy (multi-language)
    marketing_en = generate_marketing_texts(filepath, "English")
    marketing_cn = generate_marketing_texts(filepath, "Chinese")
    marketing_fr = generate_marketing_texts(filepath, "French")

    # Store result in session-like dict to allow downloading later
    global last_result
    last_result = {
        "image": filepath,
        "caption_llava": caption_llava,
        "caption_bak": caption_bak,
        "tags": tags,
        "marketing_en": marketing_en,
        "marketing_cn": marketing_cn,
        "marketing_fr": marketing_fr,
    }

    return render_template(
        "result.html",
        image_url=filepath,
        caption_llava=caption_llava,
        caption_bak=caption_bak,
        tags=tags,
        marketing_en=marketing_en,
        marketing_cn=marketing_cn,
        marketing_fr=marketing_fr,
        answer=None
    )


@app.route("/ask", methods=["POST"])
def ask():

    image_path = request.form["image_path"]
    question = request.form["question"]

    answer = ollama_vision(
        "llava:7b",
        f"Answer this question based on the image: {question}",
        image_path
    )

    return render_template(
        "result.html",
        image_url=image_path,
        caption_llava="(same as before)",
        caption_bak="(same as before)",
        tags=[],
        marketing_en={},
        marketing_cn={},
        marketing_fr={},
        answer=answer
    )


# ------------------------------
# PDF DOWNLOAD
# ------------------------------
@app.route("/download/pdf")
def download_pdf():

    if "last_result" not in globals():
        return "No result available", 400

    data = last_result
    pdf_path = f"{TEMP_FOLDER}/result.pdf"

    c = canvas.Canvas(pdf_path, pagesize=letter)
    width, height = letter

    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 40, "AI Image Caption Report")

    # Image
    try:
        img = ImageReader(data["image"])
        c.drawImage(img, 50, height - 300, width=250, preserveAspectRatio=True)
    except:
        c.drawString(50, height - 80, "(Unable to load image)")

    y = height - 330
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "LLaVA Caption:")
    c.setFont("Helvetica", 10)
    y -= 15
    for line in data["caption_llava"].split("\n"):
        c.drawString(50, y, line)
        y -= 12

    y -= 15
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "BakLLaVA Caption:")
    c.setFont("Helvetica", 10)
    y -= 15
    for line in data["caption_bak"].split("\n"):
        c.drawString(50, y, line)
        y -= 12

    y -= 20
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Tags:")
    y -= 15
    c.setFont("Helvetica", 10)
    c.drawString(50, y, ", ".join(data["tags"]))

    # Marketing blocks
    def draw_block(title, block):
        nonlocal y
        y -= 40
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, title)
        y -= 15
        c.setFont("Helvetica", 10)
        for key, text in block.items():
            c.drawString(50, y, f"- {key}: ")
            y -= 12
            for line in text.split("\n"):
                c.drawString(70, y, line)
                y -= 12
            y -= 6

    draw_block("English Marketing:", data["marketing_en"])
    draw_block("Chinese Marketing:", data["marketing_cn"])
    draw_block("French Marketing:", data["marketing_fr"])

    c.save()

    return send_file(pdf_path, as_attachment=True)



# ------------------------------
# ZIP DOWNLOAD
# ------------------------------
@app.route("/download/zip")
def download_zip():

    if "last_result" not in globals():
        return "No result available", 400

    data = last_result
    zip_path = f"{TEMP_FOLDER}/result.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:

        # Add image
        z.write(data["image"], arcname="image.jpg")

        # Captions
        captions_text = f"LLaVA:\n{data['caption_llava']}\n\nBakLLaVA:\n{data['caption_bak']}"
        z.writestr("captions.txt", captions_text)

        # Tags
        z.writestr("tags.txt", ", ".join(data["tags"]))

        # Marketing EN/CN/FR
        z.writestr("marketing_en.json", json.dumps(data["marketing_en"], indent=4))
        z.writestr("marketing_cn.json", json.dumps(data["marketing_cn"], indent=4))
        z.writestr("marketing_fr.json", json.dumps(data["marketing_fr"], indent=4))

        # Metadata
        z.writestr("metadata.json", json.dumps({
            "image": data["image"],
            "tags": data["tags"]
        }, indent=4))

    return send_file(zip_path, as_attachment=True)



# ------------------------------
# Run App
# ------------------------------
if __name__ == "__main__":
    app.run(debug=True)
