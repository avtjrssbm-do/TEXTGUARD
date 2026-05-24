from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

from docx import Document
from PyPDF2 import PdfReader

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

import os
import shutil
import requests
import re
import time


# ======================================================
# FASTAPI
# ======================================================

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ======================================================
# FOLDERS
# ======================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
DATABASE_FOLDER = os.path.join(BASE_DIR, "documents_db")

API_URL = "https://api.languagetool.org/v2/check"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DATABASE_FOLDER, exist_ok=True)


# ======================================================
# FILE READERS
# ======================================================

def load_txt(path):

    with open(
        path,
        "r",
        encoding="utf-8",
        errors="ignore"
    ) as f:

        return f.read()


def load_docx(path):

    doc = Document(path)

    return "\n".join(
        p.text
        for p in doc.paragraphs
        if p.text.strip()
    )


def load_pdf(path):

    reader = PdfReader(path)

    text = ""

    for page in reader.pages:

        try:

            page_text = page.extract_text()

            if page_text:
                text += page_text + "\n"

        except Exception as e:

            print("Ошибка PDF:", e)

    return text


def extract_text(path):

    ext = os.path.splitext(path)[1].lower()

    try:

        if ext == ".txt":
            return load_txt(path)

        elif ext == ".docx":
            return load_docx(path)

        elif ext == ".pdf":
            return load_pdf(path)

    except Exception as e:

        print("Ошибка чтения файла:", e)

    return ""


# ======================================================
# CLEAN TEXT
# ======================================================

def clean_text(text):

    text = text.lower()

    text = re.sub(
        r"[^\w\s]",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ======================================================
# SPLIT TEXT
# ======================================================

def split_text(text):

    text = clean_text(text)

    words = text.split()

    parts = []

    chunk_size = 40

    for i in range(
        0,
        len(words),
        chunk_size
    ):

        chunk = " ".join(
            words[i:i + chunk_size]
        )

        if len(chunk) > 50:

            parts.append(chunk)

    return parts


# ======================================================
# SPELLING CHECK
# ======================================================

def check_spelling(text):

    try:

        response = requests.post(

            API_URL,

            data={
                "text": text,
                "language": "ru"
            },

            timeout=15
        )

        data = response.json()

    except Exception as e:

        print("Ошибка проверки:", e)

        return []

    errors = []

    seen = set()

    for m in data.get("matches", []):

        word = text[
            m["offset"]:
            m["offset"] + m["length"]
        ]

        if word in seen:
            continue

        seen.add(word)

        errors.append({

            "word":
            word,

            "message":
            m["message"],

            "replacements": [

                x["value"]

                for x in
                m.get(
                    "replacements",
                    []
                )[:5]

            ]

        })

    return errors


# ======================================================
# PLAGIARISM
# ======================================================

def check_plagiarism(text):

    input_parts = split_text(text)

    if len(input_parts) == 0:

        return (
            0,
            "Нет текста"
        )

    best_score = 0
    best_source = ""

    files = os.listdir(DATABASE_FOLDER)

    print("ФАЙЛЫ В БАЗЕ:", files)

    if len(files) == 0:

        return (
            0,
            "База пуста"
        )

    for file in files:

        path = os.path.join(
            DATABASE_FOLDER,
            file
        )

        print("ПРОВЕРКА:", path)

        try:

            db_text = extract_text(path)

            if not db_text.strip():

                print("Пустой текст:", file)

                continue

            db_parts = split_text(db_text)

            if len(db_parts) == 0:

                print("Нет частей:", file)

                continue

            matches = 0

            for input_chunk in input_parts:

                texts = [input_chunk] + db_parts

                vectorizer = TfidfVectorizer()

                matrix = vectorizer.fit_transform(
                    texts
                )

                similarity = cosine_similarity(
                    matrix[0:1],
                    matrix[1:]
                )

                max_similarity = similarity.max()

                if max_similarity >= 0.3:

                    matches += 1

            score = round(

                matches /
                len(input_parts)
                * 100,

                2
            )

            print("СОВПАДЕНИЕ:", file, score)

            if score > best_score:

                best_score = score
                best_source = file

        except Exception as e:

            print(
                "Ошибка плагиата:",
                e
            )

    return (
        best_score,
        best_source
    )


# ======================================================
# ADD FILE TO DATABASE
# ======================================================

@app.post("/add_to_database")
async def add_to_database(
    file: UploadFile = File(...)
):

    filepath = os.path.join(
        DATABASE_FOLDER,
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

    print("ФАЙЛ ДОБАВЛЕН:", filepath)

    return {

        "message":
        "Файл добавлен в базу",

        "filename":
        file.filename

    }


# ======================================================
# CHECK FILE
# ======================================================

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

    print("ПРОВЕРЯЕМ:", filepath)

    text = extract_text(filepath)

    errors = check_spelling(text)

    plagiarism, source = check_plagiarism(text)

    return {

        "filename":
        file.filename,

        "text":
        text,

        "plagiarism":
        plagiarism,

        "uniqueness":
        round(
            100 - plagiarism,
            2
        ),

        "source":
        source,

        "errors_count":
        len(errors),

        "errors":
        errors[:50],

        "time":
        round(
            time.time() - start,
            2
        )

    }


# ======================================================
# HOME
# ======================================================

@app.get("/")
def home():

    return {

        "status":
        "TextGuard API running",

        "database_path":
        DATABASE_FOLDER

    }