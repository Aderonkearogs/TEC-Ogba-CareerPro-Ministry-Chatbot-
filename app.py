import re
from pathlib import Path
from difflib import SequenceMatcher

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


# ============================================================
# BASIC SETUP
# ============================================================

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
KB_PATH = ROOT / "knowledge_base.txt"
LOGO_PATH = ROOT / "elevation-church-logo.png"

app = FastAPI(
    title="The Elevation Church Ogba CareerPro Ministry Chatbot"
)


# ============================================================
# STATIC FILES: CHURCH LOGO
# ============================================================

app.mount(
    "/static",
    StaticFiles(directory=str(ROOT)),
    name="static",
)


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize(text: str) -> str:
    """Convert text to lowercase and remove punctuation."""
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9₦\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# ============================================================
# KNOWLEDGE BASE LOADING
# ============================================================

QUESTION_RE = re.compile(r"^\s*Q:\s*(.*?)\s*$", re.IGNORECASE)
ANSWER_RE = re.compile(r"^\s*A:\s*(.*?)\s*$", re.IGNORECASE)

NUMBERED_HEADING_RE = re.compile(
    r"^\s*\d{1,3}\s*[.)-]\s+[A-Z][A-Z0-9 /&()'’:-]{2,}\s*$"
)

DOCUMENT_HEADING_RE = re.compile(
    r"^\s*(SECTION\s+\d+|APPENDIX|TABLE OF CONTENTS|"
    r"FREQUENTLY ASKED QUESTIONS|KNOWLEDGE BASE)\b.*$",
    re.IGNORECASE,
)


def is_document_heading(line: str) -> bool:
    """Identify likely standalone document headings."""
    return bool(
        NUMBERED_HEADING_RE.match(line)
        or DOCUMENT_HEADING_RE.match(line)
    )


def load_knowledge_base():
    """
    Load explicit Q&A records from knowledge_base.txt.

    Supported format:

    Q: What is CareerPro Ministry?
    A: CareerPro Ministry is...
       Additional answer lines are allowed.

    Each answer ends at the next Q: record or a detected
    standalone document heading.
    """

    if not KB_PATH.is_file():
        raise FileNotFoundError(
            f"Knowledge base not found: {KB_PATH}"
        )

    text = KB_PATH.read_text(encoding="utf-8-sig")

    records = []
    current_question = None
    answer_lines = []
    reading_answer = False
    malformed_questions = []

    def save_record():
        nonlocal current_question, answer_lines, reading_answer

        if current_question:
            answer = "\n".join(answer_lines).strip()

            if reading_answer and answer:
                records.append({
                    "question": current_question,
                    "answer": answer,
                })
            else:
                malformed_questions.append(current_question)

        current_question = None
        answer_lines = []
        reading_answer = False

    for line in text.splitlines():
        question_match = QUESTION_RE.match(line)
        answer_match = ANSWER_RE.match(line)

        if question_match:
            save_record()
            current_question = question_match.group(1).strip()
            continue

        if answer_match and current_question and not reading_answer:
            answer_lines.append(answer_match.group(1).strip())
            reading_answer = True
            continue

        if current_question and reading_answer:
            stripped = line.strip()

            if not stripped:
                if answer_lines and answer_lines[-1] != "":
                    answer_lines.append("")
                continue

            if is_document_heading(stripped):
                save_record()
                continue

            answer_lines.append(stripped)

    save_record()

    # Remove exact duplicate records without changing their order.
    unique_records = []
    seen = set()

    for record in records:
        key = (
            normalize(record["question"]),
            normalize(record["answer"]),
        )

        if key not in seen:
            seen.add(key)
            unique_records.append(record)

    if not unique_records:
        raise ValueError(
            "No valid Q&A records were found in knowledge_base.txt. "
            "Use entries formatted as Q: followed by A:."
        )

    if malformed_questions:
        print(
            "WARNING: Questions with missing answers were ignored: "
            + "; ".join(malformed_questions[:10])
        )

    print(
        f"Loaded {len(unique_records)} Q&A records "
        f"from {KB_PATH.name}"
    )

    return unique_records


try:
    QA_RECORDS = load_knowledge_base()
    KB_LOAD_ERROR = None

except Exception as error:
    QA_RECORDS = []
    KB_LOAD_ERROR = str(error)
    print(f"ERROR loading knowledge base: {KB_LOAD_ERROR}")


# ============================================================
# GREETING HANDLING
# ============================================================

GREETING_PATTERNS = [
    r"hi",
    r"hello",
    r"hey",
    r"hiya",
    r"good morning",
    r"good afternoon",
    r"good evening",
    r"how are you",
    r"how are you doing",
    r"thank you",
    r"thanks",
    r"bye",
    r"goodbye",
    r"see you",
]


def detect_greeting(question: str):
    """Respond to greetings without searching for unrelated answers."""
    text = normalize(question)

    if not text:
        return None

    for greeting in GREETING_PATTERNS:
        if text == greeting or text.startswith(greeting + " "):
            if greeting in {"bye", "goodbye", "see you"}:
                return (
                    "Thank you for visiting the CareerPro Ministry "
                    "chatbot. Have a blessed day!"
                )

            if greeting in {"thanks", "thank you"}:
                return (
                    "You're welcome! What would you like to know "
                    "about CareerPro Ministry?"
                )

            if greeting in {"how are you", "how are you doing"}:
                return (
                    "I'm here and ready to help. What would you like "
                    "to know about CareerPro Ministry?"
                )

            return (
                "Hello! Welcome to The Elevation Church Ogba "
                "CareerPro Ministry chatbot. You can ask me about "
                "the ministry, programmes, registration, events, "
                "mentorship, and career opportunities."
            )

    return None


# ============================================================
# QUESTION MATCHING
# ============================================================

STOP_WORDS = {
    "what", "who", "where", "when", "why", "how",
    "does", "do", "did", "can", "could", "would",
    "should", "is", "are", "was", "were", "the",
    "a", "an", "and", "or", "of", "to", "for",
    "in", "on", "with", "about", "tell", "me",
    "please", "i", "my", "you", "your", "we",
    "they", "it", "this", "that", "there", "be",
    "am", "as", "at", "from", "by",
}


def useful_words(text: str) -> set[str]:
    """Extract meaningful words from a question."""
    return {
        word
        for word in normalize(text).split()
        if len(word) > 2 and word not in STOP_WORDS
    }


SYNONYM_GROUPS = [
    {
        "job", "jobs", "employment", "work", "vacancy",
        "vacancies", "role", "roles", "opportunity",
        "opportunities",
    },
    {
        "career", "careers", "professional",
        "profession", "occupation",
    },
    {
        "ministry", "programme", "program", "initiative",
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
        "join", "joining", "register", "registration",
        "signup", "enrol", "enroll",
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
        "activity", "activities", "event", "events",
        "session", "sessions",
    },
    {
        "date", "dates", "time", "schedule",
    },
    {
        "location", "venue", "address",
    },
    {
        "contact", "contacts", "reach",
        "message", "connect",
    },
]


def expand_synonyms(words: set[str]) -> set[str]:
    """Expand meaningful words with related terms."""
    expanded = set(words)

    for group in SYNONYM_GROUPS:
        if expanded.intersection(group):
            expanded.update(group)

    return expanded


def is_generic_fallback(record: dict) -> bool:
    """Exclude generic fallback entries from normal matching."""
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


def fuzzy_similarity(first: str, second: str) -> float:
    """Compare two normalized strings."""
    first = normalize(first)
    second = normalize(second)

    if not first or not second:
        return 0.0

    return SequenceMatcher(None, first, second).ratio()


def keyword_similarity(
    user_question: str,
    stored_question: str,
) -> float:
    """Compare meaningful words in two questions."""
    user_words = expand_synonyms(useful_words(user_question))
    stored_words = expand_synonyms(useful_words(stored_question))

    if not user_words or not stored_words:
        return 0.0

    overlap = user_words & stored_words

    user_coverage = len(overlap) / len(user_words)
    stored_coverage = len(overlap) / len(stored_words)

    return user_coverage * 0.65 + stored_coverage * 0.35


def phrase_bonus(
    user_question: str,
    stored_question: str,
) -> float:
    """Reward exact or contained phrase matches."""
    user_text = normalize(user_question)
    stored_text = normalize(stored_question)

    if not user_text or not stored_text:
        return 0.0

    if user_text == stored_text:
        return 1.0

    if len(user_text) >= 5 and (
        user_text in stored_text
        or stored_text in user_text
    ):
        return 0.6

    return 0.0


def retrieve_best_match(user_question: str):
    """Return the strongest sufficiently relevant Q&A record."""
    if not QA_RECORDS:
        return None

    user_text = normalize(user_question)
    user_words = useful_words(user_question)

    # Avoid choosing arbitrary records for greetings or vague input.
    if not user_words:
        return None

    candidates = []

    for record in QA_RECORDS:
        if is_generic_fallback(record):
            continue

        stored_question = record["question"]
        stored_words = useful_words(stored_question)

        fuzzy_score = fuzzy_similarity(
            user_text,
            stored_question,
        )

        keyword_score = keyword_similarity(
            user_question,
            stored_question,
        )

        phrase_score = phrase_bonus(
            user_question,
            stored_question,
        )

        score = (
            fuzzy_score * 0.25
            + keyword_score * 0.60
            + phrase_score * 0.15
        )

        if user_text == normalize(stored_question):
            score = 1.0

        # Fuzzy wording alone must not match unrelated topics.
        expanded_user = expand_synonyms(user_words)
        expanded_stored = expand_synonyms(stored_words)

        if not expanded_user.intersection(expanded_stored):
            score = min(score, 0.25)

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
        reverse=True,
    )

    best = candidates[0]

    if best["score"] < 0.45:
        return None

    if len(candidates) > 1:
        second = candidates[1]
        difference = best["score"] - second["score"]

        if best["score"] < 0.60 and difference < 0.07:
            return None

    return best


# ============================================================
# REQUEST MODEL
# ============================================================

class AskRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=2,
        max_length=1000,
    )


# ============================================================
# WEBPAGE ROUTE
# ============================================================

@app.get("/")
async def home():
    """Serve index.html from web/ or the app directory."""
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
            "Chatbot web page not found. Ensure index.html is "
            "inside the web/ folder or beside app.py."
        ),
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
async def health():
    """Report application and knowledge-base status."""
    return {
        "status": "ok",
        "service": "careerpro-ministry-chatbot",
        "knowledge_base_loaded": bool(QA_RECORDS),
        "qa_records_loaded": len(QA_RECORDS),
        "knowledge_base_file_exists": KB_PATH.is_file(),
        "web_folder_exists": WEB_DIR.is_dir(),
        "web_index_exists": (WEB_DIR / "index.html").is_file(),
        "root_index_exists": (ROOT / "index.html").is_file(),
        "church_logo_exists": LOGO_PATH.is_file(),
        "church_logo_url": "/static/elevation-church-logo.png",
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

    # Handle greetings before knowledge-base retrieval.
    greeting_reply = detect_greeting(question)

    if greeting_reply:
        return {
            "answer": greeting_reply,
            "sources": [],
            "matched_question": None,
            "confidence": 1.0,
            "intent": "greeting",
        }

    if not QA_RECORDS:
        return {
            "answer": (
                "The CareerPro Ministry knowledge base is temporarily "
                "unavailable. Please contact the CareerPro Ministry team "
                "through its official communication channels."
            ),
            "sources": [],
            "matched_question": None,
        }

    result = retrieve_best_match(question)

    if result is None:
        return {
            "answer": (
                "I couldn't find enough information in the CareerPro "
                "Ministry knowledge base to answer that confidently. "
                "Please confirm this with the CareerPro Ministry team "
                "through its official communication channels."
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
    """
    return {
        "message": (
            "Use the Find a Job feature to search for current vacancies "
            "from external sources. Verify each vacancy and application "
            "link before applying."
        ),
        "live_search_enabled": False,
    }
