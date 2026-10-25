import os
import re
from pathlib import Path
from difflib import SequenceMatcher

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel


# ============================================================
# BASIC SETUP
# ============================================================

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
KB_PATH = ROOT / "knowledge_base.txt"

app = FastAPI(
    title="The Elevation Church Ogba CareerPro Ministry Chatbot"
)


# ============================================================
# KNOWLEDGE BASE LOADING
# ============================================================

def load_knowledge_base():
    """
    Reads knowledge_base.txt and converts it into individual
    Question / Answer records.

    Expected format:

    Q: What is CareerPro Ministry?
    A: CareerPro Ministry is...

    Q: Who leads CareerPro?
    A: Aderonke Shogbola...
    """

    if not KB_PATH.exists():
        raise FileNotFoundError(
            f"Knowledge base not found: {KB_PATH}"
        )

    text = KB_PATH.read_text(encoding="utf-8")

    # Split every time a new Q: begins.
    blocks = re.split(r"(?m)(?=^Q:\s*)", text)

    records = []

    for block in blocks:
        block = block.strip()

        if not block.startswith("Q:"):
            continue

        lines = block.splitlines()

        question = ""
        answer_lines = []

        for line in lines:
            stripped = line.strip()

            if stripped.startswith("Q:"):
                question = stripped[2:].strip()

            elif stripped.startswith("A:"):
                answer_lines.append(stripped[2:].strip())

            elif answer_lines:
                # Continue multiline answers.
                if stripped:
                    answer_lines.append(stripped)

        answer = "\n".join(answer_lines).strip()

        if question and answer:
            records.append(
                {
                    "question": question,
                    "answer": answer,
                }
            )

    return records


try:
    QA_RECORDS = load_knowledge_base()
except Exception as e:
    QA_RECORDS = []
    print(f"ERROR loading knowledge base: {e}")


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize(text):
    """
    Makes text easier to compare.

    Example:
    "What does CareerPro Ministry do?"
    becomes something like:
    "what does careerpro ministry do"
    """

    text = text.lower()

    # Remove punctuation but keep ₦ and letters/numbers.
    text = re.sub(r"[^a-z0-9₦\s]", " ", text)

    # Remove repeated spaces.
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def get_words(text):
    """
    Returns useful individual words.
    """

    normalized = normalize(text)

    return set(
        word
        for word in normalized.split()
        if len(word) > 2
    )


# ============================================================
# COMMON WORDS
# ============================================================

STOP_WORDS = {
    "what",
    "who",
    "where",
    "when",
    "why",
    "how",
    "does",
    "do",
    "did",
    "can",
    "could",
    "would",
    "should",
    "is",
    "are",
    "was",
    "were",
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "to",
    "for",
    "in",
    "on",
    "with",
    "about",
    "tell",
    "me",
    "please",
    "i",
    "my",
    "you",
    "your",
    "we",
    "they",
    "it",
}


def useful_words(text):
    words = get_words(text)

    return {
        word
        for word in words
        if word not in STOP_WORDS
    }


# ============================================================
# CAREERPRO SYNONYMS
# ============================================================

# These help when the user asks the same thing in a
# different way from the wording in knowledge_base.txt.

SYNONYM_GROUPS = [
    {
        "job",
        "jobs",
        "employment",
        "work",
        "vacancy",
        "vacancies",
        "role",
        "roles",
        "opportunity",
        "opportunities",
    },
    {
        "career",
        "careers",
        "professional",
        "profession",
        "work",
    },
    {
        "ministry",
        "programme",
        "program",
        "initiative",
    },
    {
        "business",
        "businesses",
        "enterprise",
        "entrepreneur",
        "entrepreneurship",
    },
    {
        "funding",
        "fund",
        "grant",
        "grants",
        "financial",
        "support",
        "money",
    },
    {
        "mentor",
        "mentoring",
        "mentorship",
    },
    {
        "join",
        "joining",
        "register",
        "registration",
        "signup",
        "sign",
    },
    {
        "start",
        "starts",
        "started",
        "begin",
        "begins",
        "beginning",
        "next",
    },
    {
        "prayer",
        "prayers",
        "pray",
        "praying",
    },
    {
        "testimony",
        "testimonies",
        "testify",
        "story",
    },
    {
        "leader",
        "leadership",
        "head",
        "leads",
    },
    {
        "activity",
        "activities",
        "event",
        "events",
        "session",
        "sessions",
    },
]


def expand_synonyms(words):
    """
    Expands a set of words using our simple CareerPro
    synonym groups.

    Example:
    "jobs" can also match "employment", "vacancy",
    "opportunity", etc.
    """

    expanded = set(words)

    for group in SYNONYM_GROUPS:
        if expanded.intersection(group):
            expanded.update(group)

    return expanded


# ============================================================
# SIMILARITY FUNCTIONS
# ============================================================

def fuzzy_similarity(user_question, stored_question):
    """
    Compares the overall wording of two questions.
    Returns a number between 0 and 1.
    """

    user_text = normalize(user_question)
    stored_text = normalize(stored_question)

    if not user_text or not stored_text:
        return 0.0

    return SequenceMatcher(
        None,
        user_text,
        stored_text
    ).ratio()


def keyword_similarity(user_question, stored_question):
    """
    Compares important words between the user's question
    and the stored question.
    """

    user_words = expand_synonyms(
        useful_words(user_question)
    )

    stored_words = expand_synonyms(
        useful_words(stored_question)
    )

    if not user_words or not stored_words:
        return 0.0

    overlap = user_words.intersection(stored_words)

    # How much of the user's important vocabulary was matched?
    user_coverage = len(overlap) / len(user_words)

    # How much of the stored question was matched?
    stored_coverage = len(overlap) / len(stored_words)

    # Balanced score.
    return (
        user_coverage * 0.65
        + stored_coverage * 0.35
    )


def phrase_bonus(user_question, stored_question):
    """
    Gives extra points when an important phrase appears
    in both questions.
    """

    user_text = normalize(user_question)
    stored_text = normalize(stored_question)

    bonus = 0.0

    # Exact question match.
    if user_text == stored_text:
        bonus += 0.40

    # One question contains the other.
    elif user_text in stored_text or stored_text in user_text:
        bonus += 0.20

    return bonus


# ============================================================
# SPECIAL HANDLING FOR GENERIC FALLBACK QUESTIONS
# ============================================================

def is_generic_fallback(record):
    """
    Prevents the generic 'question not covered' entry in the
    knowledge base from accidentally matching every question.
    """

    question = normalize(record["question"])

    fallback_phrases = [
        "question that isn't answered here",
        "question that is not answered here",
        "questions not covered",
        "not answered here",
        "not covered",
    ]

    return any(
        phrase in question
        for phrase in fallback_phrases
    )


# ============================================================
# RETRIEVAL
# ============================================================

def retrieve_best_match(user_question):
    """
    Finds the most relevant Q&A from the knowledge base.

    We combine:
      1. Fuzzy wording similarity
      2. Keyword similarity
      3. Phrase matching
    """

    candidates = []

    for record in QA_RECORDS:

        # Do not use the generic fallback as a normal result.
        if is_generic_fallback(record):
            continue

        stored_question = record["question"]

        fuzzy_score = fuzzy_similarity(
            user_question,
            stored_question
        )

        keyword_score = keyword_similarity(
            user_question,
            stored_question
        )

        phrase_score = phrase_bonus(
            user_question,
            stored_question
        )

        # Weighted final score.
        final_score = (
            (fuzzy_score * 0.45)
            + (keyword_score * 0.45)
            + (phrase_score * 0.10)
        )

        candidates.append(
            {
                "record": record,
                "score": final_score,
                "fuzzy": fuzzy_score,
                "keyword": keyword_score,
            }
        )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    best = candidates[0]

    # --------------------------------------------------------
    # CONFIDENCE THRESHOLD
    # --------------------------------------------------------
    #
    # This is important.
    #
    # We don't want the bot to answer just because one word
    # happened to match.
    #

    if best["score"] < 0.42:
        return None

    # --------------------------------------------------------
    # TOP-TWO MARGIN CHECK
    # --------------------------------------------------------
    #
    # If two answers are almost equally likely, we should
    # avoid confidently selecting one.
    #

    if len(candidates) > 1:

        second = candidates[1]

        difference = (
            best["score"] - second["score"]
        )

        if best["score"] < 0.55 and difference < 0.04:
            return None

    return best


# ============================================================
# FASTAPI MODELS
# ============================================================

class AskRequest(BaseModel):
    question: str


# ============================================================
# WEB PAGE
# ============================================================

@app.get("/")
async def home():

    index_path = WEB_DIR / "index.html"

    if not index_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Chatbot web page not found."
        )

    return FileResponse(index_path)


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
async def health():

    return {
        "status": "ok",
        "service": "careerpro-ministry-chatbot",
        "knowledge_base_loaded": bool(QA_RECORDS),
        "qa_records_loaded": len(QA_RECORDS),
    }


# ============================================================
# CHATBOT ENDPOINT
# ============================================================

@app.post("/api/ask")
async def ask(body: AskRequest):

    question = body.question.strip()

    if len(question) < 2:
        raise HTTPException(
            status_code=400,
            detail="Please enter a question."
        )

    result = retrieve_best_match(question)

    # --------------------------------------------------------
    # NO CONFIDENT MATCH
    # --------------------------------------------------------

    if result is None:

        return {
            "answer": (
                "I couldn't find enough information in the "
                "CareerPro Ministry knowledge base to answer "
                "that confidently. Please confirm this with "
                "the CareerPro Ministry team through its "
                "official communication channels."
            ),
            "sources": [],
            "matched_question": None,
        }

    # --------------------------------------------------------
    # RETURN ONLY THE KNOWLEDGE-BASE ANSWER
    # --------------------------------------------------------

    record = result["record"]

    return {
        "answer": record["answer"],
        "sources": ["knowledge_base.txt"],
        "matched_question": record["question"],
        "confidence": round(result["score"], 3),
    }


# ============================================================
# JOB SEARCH INFORMATION
# ============================================================

@app.get("/api/search")
async def job_search_info():

    return {
        "message": (
            "Use the Find a Job feature to search for "
            "current vacancies. Current job information "
            "should come from verified external sources."
        )
    }
