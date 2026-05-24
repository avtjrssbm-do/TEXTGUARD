from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from docx import Document
from PyPDF2 import PdfReader

import os
import shutil
import requests
import re
import time

from difflib import SequenceMatcher


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


# =========================
# ЧТЕНИЕ ФАЙЛОВ
# =========================

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

            page_text=page.extract_text()

            if page_text:

                text+=page_text+"\n"

        except:

            pass

    return text


def extract_text(path):

    ext=os.path.splitext(
        path
    )[1].lower()

    try:

        if ext==".txt":
            return load_txt(path)

        elif ext==".docx":
            return load_docx(path)

        elif ext==".pdf":
            return load_pdf(path)

    except Exception as e:

        print("Ошибка:",e)

    return ""


# =========================
# ОЧИСТКА ТЕКСТА
# =========================

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


# =========================
# ПРОВЕРКА ОШИБОК
# =========================

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

    seen=set()

    for m in data.get(
        "matches",
        []
    ):

        word=text[
            m["offset"]:
            m["offset"]+
            m["length"]
        ]

        if word in seen:
            continue

        seen.add(word)

        errors.append({

            "word":
            word,

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


# =========================
# ПЛАГИАТ
# =========================

def check_plagiarism(text):

    input_text=clean_text(
        text
    )

    max_score=0
    source=""

    for root,dirs,files in os.walk(
        DATABASE_FOLDER
    ):

        for filename in files:

            path=os.path.join(
                root,
                filename
            )

            content=extract_text(
                path
            )

            content=clean_text(
                content
            )

            if not content:

                continue


            # точное совпадение

            if content==input_text:

                return(
                    100,
                    filename
                )


            similarity=SequenceMatcher(
                None,
                input_text,
                content
            ).ratio()


            score=round(
                similarity*100,
                2
            )


            if score>max_score:

                max_score=score
                source=filename


    return(
        max_score,
        source
    )


# =========================
# API
# =========================

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