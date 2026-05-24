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


app=FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_FOLDER="uploads"
DATABASE_FOLDER="documents_db"

API_URL="https://api.languagetool.org/v2/check"

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)

os.makedirs(
    DATABASE_FOLDER,
    exist_ok=True
)


# ==========================
# ЧТЕНИЕ ФАЙЛОВ
# ==========================

def load_txt(path):

    with open(
        path,
        "r",
        encoding="utf-8",
        errors="ignore"
    ) as f:

        return f.read()


def load_docx(path):

    doc=Document(path)

    return "\n".join(

        p.text

        for p in doc.paragraphs

        if p.text.strip()

    )


def load_pdf(path):

    reader=PdfReader(path)

    text=""

    for page in reader.pages:

        try:

            text+=page.extract_text() or ""

        except:
            pass

    return text


def extract_text(path):

    ext=os.path.splitext(
        path
    )[1].lower()

    if ext==".txt":
        return load_txt(path)

    elif ext==".docx":
        return load_docx(path)

    elif ext==".pdf":
        return load_pdf(path)

    return ""


# ==========================
# ОЧИСТКА
# ==========================

def clean_text(text):

    text=text.lower()

    text=re.sub(
        r"[^\w\s]",
        "",
        text
    )

    text=re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ==========================
# ПРОВЕРКА ОШИБОК
# ==========================

def check_spelling(text):

    try:

        response=requests.post(
            API_URL,
            data={
                "text":text,
                "language":"ru"
            },
            timeout=15
        )

        data=response.json()

    except:

        return []

    errors=[]

    for m in data.get(
        "matches",
        []
    ):

        errors.append({

            "word":
            text[
                m["offset"]:
                m["offset"]+
                m["length"]
            ],

            "message":
            m["message"],

            "replacements":[

                x["value"]

                for x in
                m.get(
                    "replacements",
                    []
                )[:5]

            ]

        })

    return errors


# ==========================
# ПЛАГИАТ
# ==========================

def check_plagiarism(text):

    input_text=clean_text(
        text
    )

    docs=[]

    for file in os.listdir(
        DATABASE_FOLDER
    ):

        path=os.path.join(
            DATABASE_FOLDER,
            file
        )

        try:

            content=extract_text(
                path
            )

            content=clean_text(
                content
            )

            if content:

                docs.append(
                    (
                        file,
                        content
                    )
                )

        except:
            pass


    if len(docs)==0:

        return(
            0,
            "База пуста"
        )


    for file,content in docs:

        if content==input_text:

            return(
                100,
                file
            )


    texts=[

        x[1]

        for x in docs

    ]

    texts.append(
        input_text
    )


    vectorizer=TfidfVectorizer()

    matrix=vectorizer.fit_transform(
        texts
    )


    similarity=cosine_similarity(

        matrix[-1],
        matrix[:-1]

    )


    score=float(
        similarity.max()
    )*100


    index=similarity.argmax()

    source=docs[index][0]


    return(
        round(score,2),
        source
    )


# ==========================
# ДОБАВИТЬ В БАЗУ
# ==========================

@app.post("/add_to_database")
async def add_to_database(
    file:UploadFile=File(...)
):

    filepath=os.path.join(
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

    return{

        "message":
        "Файл добавлен",

        "filename":
        file.filename

    }


# ==========================
# ПРОВЕРКА
# ==========================

@app.post("/check")
async def check(
    file:UploadFile=File(...)
):

    start=time.time()

    filepath=os.path.join(
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


    text=extract_text(
        filepath
    )

    errors=check_spelling(
        text
    )

    plagiarism,source=check_plagiarism(
        text
    )


    return{

        "filename":
        file.filename,

        "text":
        text,

        "plagiarism":
        plagiarism,

        "uniqueness":
        round(
            100-plagiarism,
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
            time.time()-start,
            2
        )

    }


@app.get("/")
def home():

    return{

        "status":
        "TextGuard API running"

    }