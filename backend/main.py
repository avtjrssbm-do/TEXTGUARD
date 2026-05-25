from typing import List
from pydantic import BaseModel
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

from docx import Document
from PyPDF2 import PdfReader

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

import zipfile
import os
import shutil
import requests
import re
import time


# ======================================================
# FASTAPI
# ======================================================

app=FastAPI()

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

BASE_DIR=os.path.dirname(
    os.path.abspath(__file__)
)

UPLOAD_FOLDER=os.path.join(
    BASE_DIR,
    "uploads"
)

USER_DATABASE_FOLDER=os.path.join(
    BASE_DIR,
    "user_database"
)

API_URL="https://api.languagetool.org/v2/check"

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)

os.makedirs(
    USER_DATABASE_FOLDER,
    exist_ok=True
)


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

        print(e)

    return ""


# ======================================================
# CLEAN
# ======================================================

def clean_text(text):

    text=text.lower()

    text=re.sub(
        r"[^\w\s]",
        " ",
        text
    )

    text=re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ======================================================
# SPLIT
# ======================================================

def split_text(text):

    text=clean_text(text)

    words=text.split()

    parts=[]

    chunk_size=40

    for i in range(
        0,
        len(words),
        chunk_size
    ):

        chunk=" ".join(
            words[i:i+chunk_size]
        )

        if len(chunk)>50:

            parts.append(
                chunk
            )

    return parts


# ======================================================
# SPELL CHECK
# ======================================================

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


# ======================================================
# PLAGIARISM
# ======================================================

def check_plagiarism(text):

    input_parts=split_text(
        text
    )

    if len(input_parts)==0:

        return 0,"Нет текста"

    best_score=0
    best_source=""

    files=os.listdir(
        USER_DATABASE_FOLDER
    )

    if len(files)==0:

        return 0,"База пуста"

    for file in files:

        try:

            path=os.path.join(
                USER_DATABASE_FOLDER,
                file
            )

            db_text=extract_text(
                path
            )

            db_parts=split_text(
                db_text
            )

            if len(
                db_parts
            )==0:

                continue

            matches=0

            for input_chunk in input_parts:

                texts=[

                    input_chunk

                ]+db_parts

                vectorizer=TfidfVectorizer()

                matrix=vectorizer.fit_transform(
                    texts
                )

                similarity=cosine_similarity(
                    matrix[0:1],
                    matrix[1:]
                )

                if similarity.max()>0.3:

                    matches+=1


            score=round(

                matches/
                len(input_parts)
                *100,

                2
            )


            if score>best_score:

                best_score=score
                best_source=file

        except Exception as e:

            print(e)

    return best_score,best_source


# ======================================================
# DATABASE MODELS
# ======================================================

class DatabaseLink(BaseModel):

    url:str


# ======================================================
# UPLOAD FILES DATABASE
# ======================================================

@app.post("/upload_database")

async def upload_database(

    files:List[UploadFile]=File(...)

):

    added=[]

    for file in files:

        filepath=os.path.join(
            USER_DATABASE_FOLDER,
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

        added.append(
            file.filename
        )

    return{

        "message":"База загружена",

        "files":added
    }


# ======================================================
# LOAD DATABASE LINK
# ======================================================

@app.post("/load_database_link")

async def load_database_link(

    data:DatabaseLink

):

    try:

        temp=os.path.join(
            BASE_DIR,
            "database.zip"
        )

        response=requests.get(
            data.url
        )

        with open(
            temp,
            "wb"
        ) as f:

            f.write(
                response.content
            )


        with zipfile.ZipFile(
            temp,
            "r"
        ) as zip_ref:

            zip_ref.extractall(
                USER_DATABASE_FOLDER
            )


        os.remove(
            temp
        )

        return{

            "message":
            "База подключена"

        }

    except Exception as e:

        return{

            "error":
            str(e)

        }


# ======================================================
# CHECK
# ======================================================

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