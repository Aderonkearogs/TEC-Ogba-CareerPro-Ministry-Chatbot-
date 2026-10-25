
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
    Read knowledge_base.txt and split it into Q&A records.

    Supported format:

    Q: What is CareerPro Ministry?
    A: CareerPro Ministry is...

    Answers may continue across multiple lines.
    """

    if not KB_PATH.is_file():
        raise FileNotFoundError(
            f"Knowledge base not found: {KB_PATH}"
        )

    text = KB_PATH.read_text(encoding="utf-8-sig")

    # Each new Q: starts a new record.
    blocks = re.split(r"(?m)(?=^Q:\s*)", text)

    records = []

    for block in blocks:
        block = block.strip()

        if not block.startswith("Q:"):
            continue

        question = ""
        answer_lines = []
        reading_answer = False

        for line in block.splitlines():
            stripped = line.strip()

            if stripped.startswith("Q:"):
                question = stripped[2:].strip()
                reading_answer = False

            elif stripped.startswith("A:"):
                answer_lines.append(stripped[2:].strip())
                reading_answer = True

            elif reading_answer and stripped:
                answer_lines.append(stripped)

        answer = "\n".join(answer_lines).strip()

        if question and answer:
            records.append({
                "question": question,
                "answer": answer,
            })

    if not records:
        raise ValueError(
            "No Q&A records were found in knowledge_base.txt. "
            "Check that entries use Q: and A:."
        )

    return records


try:
    QA_RECORDS = load_knowledge_base()
    KB_LOAD_ERROR = None

except Exception as error:
    QA_RECORDS = []
    KB_LOAD_ERROR = str(error)
    print(f"ERROR loading knowledge base: {KB_LOAD_ERROR}")


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize(text):
    """Convert text to lowercase and remove punctuation."""

    text = text.lower()
    text = re.sub(r"[^a-z0-9₦\s]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


STOP_WORDS = {
    "what", "who", "where", "when", "why", "how",
    "does", "do", "did", "can", "could", "would",
    "should", "is", "are", "was", "were", "the",
    "a", "an", "and", "or", "of", "to", "for",
    "in", "on", "with", "about", "tell", "me",
    "please", "i", "my", "you", "your", "we",
    "they", "it", "this", "that", "there", "be",
    "am", "are", "as", "at", "from", "by",
}


def useful_words(text):
    """Return meaningful words from a question."""

    words = set(normalize(text).split())

    return {
        word for word in words
        if len(word) > 2 and word not in STOP_WORDS
    }


# ============================================================
# SYNONYM MATCHING
# ============================================================

SYNONYM_GROUPS = [
    {
        "job", "jobs", "employment", "work",
        "vacancy", "vacancies", "role", "roles",
        "opportunity", "opportunities",
    },
    {
        "career", "careers", "professional",
        "profession", "occupation",
    },
    {
        "ministry", "programme", "program",
        "initiative",
    },
    {
        "business", "businesses", "enterprise",
        "entrepreneur", "entrepreneurship",
    },
    {
        "funding", "fund", "grant", "grants",
        "financial", "money", "finance",
    },
    {
        "mentor", "mentoring", "mentorship",
    },
    {
        "join", "joining", "register",
        "registration", "signup", "enrol",
        "enroll",
    },
    {
        "start", "starts", "started", "begin",
        "begins", "beginning",
    },
    {
        "prayer", "prayers", "pray", "praying",
    },
    {
        "testimony", "testimonies", "testify",
        "story", "stories",
    },
    {
        "leader", "leadership", "head", "leads",
    },
    {
        "activity", "activities", "event",
        "events", "session", "sessions",
    },
    {
        "date", "dates", "time", "schedule",
        "when",
    },
    {
        "location", "venue", "address", "where",
    },
    {
        "contact", "contacts", "reach",
        "message", "connect",
    },
]


def expand_synonyms(words):
    """Add related terms to improve matching."""

    expanded = set(words)

    for group in SYNONYM_GROUPS:
        if expanded.intersection(group):
            expanded.update(group)

    return expanded


# ============================================================
# FALLBACK ENTRY DETECTION
# ============================================================

def is_generic_fallback(record):
    """Keep generic fallback answers out of normal retrieval."""

    question = normalize(record["question"])

    fallback_phrases = [
        "question that isnt answered here",
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
# SIMILARITY SCORING
# ============================================================

def fuzzy_similarity(first, second):
    """Compare the wording of two strings."""

    first = normalize(first)
    second = normalize(second)

    if not first or not second:
        return 0.0

    return SequenceMatcher(
        None, first, second
    ).ratio()


def keyword_similarity(user_question, stored_question):
    """Compare meaningful words in two questions."""

    user_words = expand_synonyms(
        useful_words(user_question)
    )

    stored_words = expand_synonyms(
        useful_words(stored_question)
    )

    if not user_words or not stored_words:
        return 0.0

    overlap = user_words & stored_words

    user_coverage = len(overlap) / len(user_words)
    stored_coverage = len(overlap) / len(stored_words)

    return (
        user_coverage * 0.65
        + stored_coverage * 0.35
    )


def phrase_bonus(user_question, stored_question):
    """Reward exact and contained phrase matches."""

    user_text = normalize(user_question)
    stored_text = normalize(stored_question)

    if not user_text or not stored_text:
        return 0.0

    if user_text == stored_text:
        return 1.0

    if (
        len(user_text) >= 5
        and (
            user_text in stored_text
            or stored_text in user_text
        )
    ):
        return 0.6

    return 0.0


def retrieve_best_match(user_question):
    """
    Retrieve the most relevant stored Q&A.

    The chatbot returns the stored answer itself. It does not
    generate new ministry facts outside the knowledge base.
    """

    if not QA_RECORDS:
        return None

    candidates = []

    user_text = normalize(user_question)

    for record in QA_RECORDS:
        if is_generic_fallback(record):
            continue

        stored_question = record["question"]

        fuzzy_score = fuzzy_similarity(
            user_text, stored_question
        )

        keyword_score = keyword_similarity(
            user_text, stored_question
        )

        phrase_score = phrase_bonus(
            user_text, stored_question
        )

        score = (
            fuzzy_score * 0.35
            + keyword_score * 0.50
            + phrase_score * 0.15
        )

        # Exact normalized question match.
        if user_text == normalize(stored_question):
            score = 1.0

        candidates.append({
            "record": record,
            "score": score,
            "fuzzy": fuzzy_score,
            "keyword": keyword_score,
        })

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    best = candidates[0]

    # Reject weak matches to avoid misleading answers.
    if best["score"] < 0.42:
        return None

    # If the two best matches are close and confidence is
    # moderate, ask the user to confirm with the ministry.
    if len(candidates) > 1:
        second = candidates[1]

        difference = best["score"] - second["score"]

        if best["score"] < 0.58 and difference < 0.05:
            return None

    return best


# ============================================================
# REQUEST MODEL
# ============================================================

class AskRequest(BaseModel):
    question: str


# ============================================================
# WEBPAGE ROUTE
# ============================================================

@app.get("/")
async def home():
    """
    Look for index.html in either supported location:
      1. web/index.html
      2. index.html beside app.py
    """

    possible_paths = [
        WEB_DIR / "index.html",
        ROOT / "index.html",
    ]

    for index_path in possible_paths:
        if index_path.is_file():
            return FileResponse(
                str(index_path),
                media_type="text/html",
            )

    raise HTTPException(
        status_code=404,
        detail=(
            "Chatbot web page not found. "
            "Please ensure index.html is committed to GitHub "
            "inside the web/ folder or beside app.py."
        ),
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
async def health():
    """Show whether the app and knowledge base loaded."""

    return {
        "status": "ok",
        "service": "careerpro-ministry-chatbot",
        "knowledge_base_loaded": bool(QA_RECORDS),
        "qa_records_loaded": len(QA_RECORDS),
        "knowledge_base_file_exists": KB_PATH.is_file(),
        "web_folder_exists": WEB_DIR.is_dir(),
        "web_index_exists": (WEB_DIR / "index.html").is_file(),
        "root_index_exists": (ROOT / "index.html").is_file(),
        "knowledge_base_error": KB_LOAD_ERROR,
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
            detail="Please enter a question.",
        )

    if not QA_RECORDS:
        return {
            "answer": (
                "The CareerPro Ministry knowledge base is "
                "temporarily unavailable. Please contact the "
                "CareerPro Ministry team through its official "
                "communication channels."
            ),
            "sources": [],
            "matched_question": None,
        }

    result = retrieve_best_match(question)

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
    """
    Informational endpoint only.

    This endpoint does not perform a live job search.
    A real job-search feature must be implemented separately
    and should return actual vacancy source/application URLs.
    """

    return {
        "message": (
            "Use the Find a Job feature to search for current "
            "vacancies from external sources. Verify each "
            "vacancy and application link before applying."
        ),
        "live_search_enabled": False,
    }
