import os
import re
from pathlib import Path
from difflib import SequenceMatcher

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
KB_PATH = ROOT / "knowledge_base.txt"

app = FastAPI(title="The Elevation Church Ogba CareerPro Ministry Chatbot")

def load_sections():
    text = KB_PATH.read_text(encoding="utf-8")
    # Keep the document's numbered topic headings as retrieval chunks.
    parts = re.split(r"(?m)(?=^\d+\.\s)", text)
    return [p.strip() for p in parts if p.strip()]

SECTIONS = load_sections()

def terms(text):
    return set(re.findall(r"[a-z0-9₦]+", text.lower()))

def retrieve(question, limit=1):
    q_terms = terms(question)
    if not q_terms:
        return []
    scored = []
    for section in SECTIONS:
        s_terms = terms(section)
        overlap = len(q_terms & s_terms)
        # Favor questions and headings containing the user's exact words.
        heading = section.splitlines()[0] if section.splitlines() else ""
        heading_bonus = len(q_terms & terms(heading)) * 1.8
        score = overlap + heading_bonus
        if score:
            scored.append((score / (len(s_terms) ** 0.25), section))
    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored or scored[0][0] < 1.0:
        return []
    return [s for _, s in scored[:limit]]

class AskRequest(BaseModel):
    question: str

@app.get("/")
async def home():
    return FileResponse("index.html")

@app.get("/health")
async def health():
    return {"status": "ok", "service": "careerpro-ministry-chatbot", "knowledge_base_loaded": bool(SECTIONS)}

@app.post("/api/ask")
async def ask(body: AskRequest):
    question = body.question.strip()
    if len(question) < 2:
        raise HTTPException(status_code=400, detail="Please enter a question.")
    matches = retrieve(question)
    if not matches:
        return {
            "answer": "I can only answer using the CareerPro Ministry knowledge base currently provided. I couldn't find enough information in that document to answer confidently. Please confirm this with the CareerPro Ministry team through its official communication channels.",
            "sources": []
        }
    # This answer is intentionally grounded in document excerpts only. No generative model is used for ministry Q&A.
    excerpts = []
    for section in matches:
        # Keep each excerpt readable and avoid dumping the entire knowledge base.
        lines = [line.strip() for line in section.splitlines() if line.strip()]
        excerpt = "\n".join(lines[:18])
        if len(excerpt) > 1800:
            excerpt = excerpt[:1800].rsplit(" ", 1)[0] + "…"
        excerpts.append(excerpt)
    answer = "\n\n".join(excerpts)
    return {"answer": answer, "sources": ["TEC OGBA CAREERPRO MINISTRY.docx"]}

@app.get("/api/search")
async def job_search_info():
    # This endpoint is only an informational hand-off. Current vacancies are searched in the browser via ChatGPT search.
    return {"message": "Use the Find a Job panel to search for current vacancies with ChatGPT/web search."}
