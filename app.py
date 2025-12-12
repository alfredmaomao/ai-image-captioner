from flask import Flask, render_template, request
import os
import base64
import requests
from datetime import datetime

app = Flask(__name__)
UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
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
# in the target language
# ------------------------------
def generate_marketing_texts(image_path, language="English"):

    prompts = {
        "ecommerce": f"Generate a persuasive e-commerce product description in {language}. Focus on selling points, emotions, and product value.",
        "xiaohongshu": f"Generate a trendy Xiaohongshu (RED) style lifestyle post in {language}. Tone: emotional, friendly, soft.",
        "instagram": f"Generate an Instagram caption in {language} with emojis and a stylish tone.",
        "seo": f"Write an SEO-optimized marketing paragraph in {language}. Include keywords and product benefits.",
        "bullets": f"List 5 concise bullet-point product features in {language}. Output bullet points only."
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

    # Save
    filename = datetime.now().strftime("%Y%m%d_%H%M%S_") + image.filename
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    image.save(filepath)

    # Captions
    caption_llava = ollama_vision("llava:7b", "Describe this image clearly.", filepath)
    caption_bak = ollama_vision("bakllava:7b", "Describe this image clearly.", filepath)

    # Tags
    raw_tags = ollama_vision(
        "llava:7b",
        "Generate 5 short keyword tags separated by commas.",
        filepath
    )
    tags = [t.strip() for t in raw_tags.split(",")]

    # Marketing copy (multi-language)
    marketing_en = generate_marketing_texts(filepath, "English")
    marketing_cn = generate_marketing_texts(filepath, "Chinese")
    marketing_fr = generate_marketing_texts(filepath, "French")

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


if __name__ == "__main__":
    app.run(debug=True)
