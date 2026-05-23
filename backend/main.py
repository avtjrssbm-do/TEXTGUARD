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


def load_txt(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_docx(path):
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs)


def load_pdf(path):
    reader = PdfReader(path)

    text = ""

    for page in reader.pages:
        text += page.extract_text() or ""

    return text


def extract_text(path):

    if path.endswith(".txt"):
        return load_txt(path)

    elif path.endswith(".docx"):
        return load_docx(path)

    elif path.endswith(".pdf"):
        return load_pdf(path)

    return ""


def check_spelling(text):

    try:

        text = text[:3000]

        r = requests.post(
            API_URL,
            data={
                "text": text,
                "language": "ru"
            },
            timeout=8
        )

        data = r.json()

    except Exception:
        return []

    errors = []

    for m in data.get("matches", []):

        errors.append({
            "word":
            text[m["offset"]:m["offset"] + m["length"]],

            "message":
            m["message"],

            "replacements":
            [x["value"] for x in m.get("replacements", [])[:3]]
        })

    return errors


def clean_text(text):

    text = text.lower()

    text = re.sub(r"\s+", " ", text)

    text = re.sub(r"[^\w\s]", "", text)

    return text.strip()


def check_plagiarism(text):

    docs = []

    for filename in os.listdir(DATABASE_FOLDER):

        path = os.path.join(
            DATABASE_FOLDER,
            filename
        )

        try:

            content = extract_text(path)

            docs.append(
                (
                    filename,
                    content
                )
            )

        except:
            continue

    if len(docs) == 0:
        return 0, "База пуста"

    cleaned_docs = [
        clean_text(d[1])
        for d in docs
    ]

    input_text = clean_text(text)

    all_texts = cleaned_docs + [
        input_text
    ]

    vectorizer = TfidfVectorizer(
        ngram_range=(2,3),
        max_features=5000
    )

    tfidf = vectorizer.fit_transform(
        all_texts
    )

    similarity = cosine_similarity(
        tfidf[-1],
        tfidf[:-1]
    )

    score = float(
        similarity.max()
    ) * 100

    index = similarity.argmax()

    source = docs[index][0]

    return round(score,2), source


@app.get("/")
def home():

    return {
        "status":"TextGuard API running"
    }


@app.post("/check")
async def check(
        file: UploadFile = File(...)
):

    start = time.time()

    filepath = os.path.join(
        UPLOAD_FOLDER,
        file.filename
    )

    with open(
        filepath,
        "wb"
    ) as buffer:

        shutil.copyfileobj(
            file.file,
            buffer
        )

    text = extract_text(
        filepath
    )

    errors = check_spelling(
        text
    )

    plagiarism, source = check_plagiarism(
        text
    )

    return {

        "filename":
        file.filename,

        "plagiarism":
        plagiarism,

        "source":
        source,

        "errors_count":
        len(errors),

        "errors":
        errors[:30],

        "time":
        round(
            time.time()-start,
            2
        )
    }