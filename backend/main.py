from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from docx import Document
from PyPDF2 import PdfReader

import os
import shutil
import requests
import re
import time

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_FOLDER = "uploads"
DATABASE_FOLDER = "documents_db"
API_URL = "https://api.languagetool.org/v2/check"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DATABASE_FOLDER, exist_ok=True)


# =========================
# ЧТЕНИЕ ФАЙЛОВ
# =========================

def load_txt(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def load_docx(path):
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def load_pdf(path):
    reader = PdfReader(path)
    text = ""
    for page in reader.pages:
        try:
            text += page.extract_text() or ""
        except:
            pass
    return text


def extract_text(path):
    ext = os.path.splitext(path)[1].lower()

    if ext == ".txt":
        return load_txt(path)
    elif ext == ".docx":
        return load_docx(path)
    elif ext == ".pdf":
        return load_pdf(path)

    return ""


# =========================
# ОЧИСТКА
# =========================

def clean_text(text):
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# =========================
# ПОДГОТОВКА ТЕКСТА (ВАЖНО)
# =========================

def split_text(text):
    text = clean_text(text)
    words = text.split()

    chunks = []
    step = 40

    for i in range(0, len(words), step):
        chunk = " ".join(words[i:i+step])
        if len(chunk) > 30:
            chunks.append(chunk)

    return chunks


# =========================
# ОШИБКИ (LanguageTool)
# =========================

def check_spelling(text):
    try:
        response = requests.post(
            API_URL,
            data={"text": text, "language": "ru"},
            timeout=15
        )
        data = response.json()
    except:
        return []

    errors = []
    seen = set()

    for m in data.get("matches", []):

        word = text[m["offset"]: m["offset"] + m["length"]]

        if word in seen:
            continue

        seen.add(word)

        errors.append({
            "word": word,
            "message": m["message"],
            "replacements": [
                r["value"] for r in m.get("replacements", [])[:5]
            ]
        })

    return errors


# =========================
# ПЛАГИАТ (ИСПРАВЛЕННЫЙ ЯДЕРНЫЙ МЕХАНИЗМ)
# =========================

def load_database():
    docs = []

    for file in os.listdir(DATABASE_FOLDER):
        path = os.path.join(DATABASE_FOLDER, file)

        try:
            text = extract_text(path)
            text = clean_text(text)

            if text:
                docs.append((file, text))

        except:
            pass

    return docs


def check_plagiarism(text):
    input_parts = split_text(text)

    if not input_parts:
        return 0, "Нет текста"

    docs = load_database()

    if not docs:
        return 0, "База пуста"

    best_score = 0
    best_file = ""

    for filename, db_text in docs:

        db_parts = split_text(db_text)

        if not db_parts:
            continue

        all_text = input_parts + db_parts

        vectorizer = TfidfVectorizer()
        matrix = vectorizer.fit_transform(all_text)

        input_vec = matrix[:len(input_parts)]
        db_vec = matrix[len(input_parts):]

        similarity = cosine_similarity(input_vec, db_vec)

        matches = 0

        for row in similarity:
            if row.max() > 0.7:
                matches += 1

        score = (matches / len(input_parts)) * 100

        if score > best_score:
            best_score = score
            best_file = filename

    return round(best_score, 2), best_file


# =========================
# ДОБАВЛЕНИЕ В БАЗУ (ВАЖНО)
# =========================

@app.post("/add_to_database")
async def add_to_database(file: UploadFile = File(...)):

    filepath = os.path.join(DATABASE_FOLDER, file.filename)

    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {
        "message": "Файл добавлен в базу",
        "filename": file.filename
    }


# =========================
# ПРОВЕРКА
# =========================

@app.post("/check")
async def check(file: UploadFile = File(...)):

    start = time.time()

    filepath = os.path.join(UPLOAD_FOLDER, file.filename)

    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    text = extract_text(filepath)

    errors = check_spelling(text)

    plagiarism, source = check_plagiarism(text)

    return {
        "filename": file.filename,
        "text": text,
        "plagiarism": plagiarism,
        "uniqueness": round(100 - plagiarism, 2),
        "source": source,
        "errors_count": len(errors),
        "errors": errors[:50],
        "time": round(time.time() - start, 2)
    }


@app.get("/")
def home():
    return {"status": "TextGuard API running"}