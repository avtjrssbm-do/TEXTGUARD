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

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)

os.makedirs(
    DATABASE_FOLDER,
    exist_ok=True
)


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

    text=[]

    for p in doc.paragraphs:

        if p.text.strip():

            text.append(
                p.text
            )

    return "\n".join(text)


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

        print(
            "Ошибка чтения:",
            path,
            e
        )

    return ""


def clean_text(text):

    text=text.lower()

    text=re.sub(
        r"\s+",
        " ",
        text
    )

    text=re.sub(
        r"[^\w\s]",
        "",
        text
    )

    return text.strip()


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

        seen.add(
            word
        )

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


def check_plagiarism(text):

    docs=[]

    input_text=clean_text(
        text
    )

    print("\n===== БАЗА =====")

    for root,dirs,files in os.walk(
        DATABASE_FOLDER
    ):

        for filename in files:

            path=os.path.join(
                root,
                filename
            )

            ext=os.path.splitext(
                filename
            )[1].lower()

            if ext not in [
                ".txt",
                ".docx",
                ".pdf"
            ]:

                continue

            try:

                content=extract_text(
                    path
                )

                content=clean_text(
                    content
                )

                if len(content)>0:

                    docs.append(
                        (
                            filename,
                            content
                        )
                    )

                    print(
                        "✓",
                        filename
                    )

            except Exception as e:

                print(
                    "Ошибка:",
                    filename,
                    e
                )


    if not docs:

        return(
            0,
            "База пуста"
        )


    # точное совпадение

    for filename,content in docs:

        if content==input_text:

            return(
                100,
                filename
            )


    all_texts=[

        d[1]

        for d in docs

    ]+[

        input_text

    ]


    vectorizer=TfidfVectorizer(

        analyzer="char_wb",
        ngram_range=(3,5)

    )


    tfidf=vectorizer.fit_transform(
        all_texts
    )


    similarity=cosine_similarity(

        tfidf[-1],
        tfidf[:-1]

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


@app.get("/")
def home():

    return{

        "status":
        "TextGuard API running"
    }


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