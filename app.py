import re
from pathlib import Path
from difflib import SequenceMatcher

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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
# CORS CONFIGURATION
# ============================================================

# Allow the separately hosted Render Static Site to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://careerpro-website.onrender.com",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


# ============================================================
# STATIC FILES
# ============================================================

# Keep the existing /static URL working.
app.mount(
    "/static",
    StaticFiles(directory=str(ROOT), check_dir=False),
    name="static",
)


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize(text: str) -> str:
    """Normalize text for matching without changing stored answers."""
    text = (text or "").lower().replace("₦", " naira ")
    text = text.replace("₦", " naira ")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text: str) -> set[str]:
    return set(normalize(text).split())


# ============================================================
# KNOWLEDGE BASE LOADING
# ============================================================

QUESTION_RE = re.compile(r"^\s*Q:\s*(.*?)\s*$", re.IGNORECASE)
ANSWER_RE = re.compile(r"^\s*A:\s*(.*?)\s*$", re.IGNORECASE)

DOCUMENT_HEADING_RE = re.compile(
    r"^\s*(?:"
    r"\d{1,3}\s*[.)-]\s+[A-Z][A-Z0-9 /&()'’:-]{2,}"
    r"|END OF KNOWLEDGE BASE"
    r")\s*$",
    re.IGNORECASE,
)


def is_document_heading(line: str) -> bool:
    return bool(DOCUMENT_HEADING_RE.match(line.strip()))


def load_knowledge_base():
    """
    Load Q&A records from knowledge_base.txt.

    Answers remain unchanged. Each answer ends at the next Q:
    entry or a standalone numbered document heading.
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

        if (
            answer_match
            and current_question
            and not reading_answer
        ):
            answer_lines.append(answer_match.group(1).strip())
            reading_answer = True
            continue

        if current_question and reading_answer:
            stripped = line.strip()

            if is_document_heading(stripped):
                save_record()
                continue

            if not stripped:
                if answer_lines and answer_lines[-1] != "":
                    answer_lines.append("")
                continue

            answer_lines.append(stripped)

    save_record()

    # Remove exact duplicates, preserving the first occurrence.
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
            "No valid Q&A records were found. "
            "Check that knowledge_base.txt contains Q: and A: entries."
        )

    if malformed_questions:
        print(
            "WARNING: Questions without valid answers were ignored: "
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

EXACT_GREETINGS = {
    "hi",
    "hello",
    "hey",
    "hiya",
    "good morning",
    "good afternoon",
    "good evening",
    "how are you",
    "how are you doing",
    "thanks",
    "thank you",
    "bye",
    "goodbye",
    "see you",
}


def detect_greeting(question: str):
    """
    Handle standalone greetings only.

    For example, 'hello, what is CareerPro?' must still
    reach knowledge-base retrieval.
    """
    text = normalize(question)

    if text not in EXACT_GREETINGS:
        return None

    if text in {"bye", "goodbye", "see you"}:
        return (
            "Thank you for visiting the CareerPro Ministry chatbot. "
            "Have a blessed day!"
        )

    if text in {"thanks", "thank you"}:
        return (
            "You're welcome! What would you like to know "
            "about CareerPro Ministry?"
        )

    if text in {"how are you", "how are you doing"}:
        return (
            "I'm here and ready to help. You can ask me about "
            "CareerPro Ministry, its programmes, career opportunities, "
            "business support, the Enterprise Development Fund, "
            "mentorship or Enterprise Month."
        )

    return (
        "Hello! Welcome to The Elevation Church Ogba CareerPro "
        "Ministry chatbot. You can ask me about the ministry, "
        "programmes, events, mentorship, job opportunities, "
        "business support and the Enterprise Development Fund."
    )


# ============================================================
# QUESTION PREPROCESSING
# ============================================================

STOP_WORDS = {
    "what", "who", "where", "when", "why", "how",
    "does", "do", "did", "can", "could", "would",
    "should", "is", "are", "was", "were", "the",
    "a", "an", "and", "or", "of", "to", "for",
    "in", "on", "with", "about", "tell", "me",
    "please", "i", "my", "you", "your", "we",
    "they", "it", "this", "that", "there", "be",
    "am", "as", "at", "from", "by", "get",
    "know", "like", "want", "need", "much",
    "more", "all", "something", "anything",
    "available", "provide", "offer", "offers",
    "support", "help", "information",
}


def useful_words(text: str) -> set[str]:
    return {
        word
        for word in tokenize(text)
        if len(word) > 2 and word not in STOP_WORDS
    }


# Expand only related terms, rather than adding every synonym
# in a group to every query. This reduces false matches.
SYNONYM_GROUPS = [
    {
        "job", "jobs", "employment", "vacancy",
        "vacancies", "role", "roles",
    },
    {
        "career", "careers", "profession",
        "professional", "occupation",
    },
    {
        "business", "businesses", "enterprise",
        "entrepreneur", "entrepreneurs", "entrepreneurship",
    },
    {
        "fund", "funding", "grant", "grants",
        "finance", "financial", "money", "capital",
    },
    {
        "mentor", "mentoring", "mentorship",
    },
    {
        "join", "register", "registration",
        "signup", "enrol", "enroll", "apply", "application",
    },
    {
        "start", "starts", "begin", "begins",
    },
    {
        "prayer", "prayers", "pray", "praying",
    },
    {
        "testimony", "testimonies", "testify",
    },
    {
        "leader", "leadership", "head", "leads",
    },
    {
        "activity", "activities", "event", "events",
    },
    {
        "date", "dates", "time", "schedule",
    },
    {
        "location", "venue", "address",
    },
    {
        "contact", "reach", "message", "connect",
    },
    {
        "loan", "loans", "borrow", "borrowing",
    },
    {
        "fee", "fees", "charge", "charges", "cost",
    },
    {
        "speaker", "speakers", "panelist", "panelists",
    },
]


def related_words(word: str) -> set[str]:
    result = {word}

    for group in SYNONYM_GROUPS:
        if word in group:
            result.update(group)

    # Common inflection handling.
    if word.endswith("ies") and len(word) > 4:
        result.add(word[:-3] + "y")

    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        result.add(word[:-1])

    if word.endswith("ing") and len(word) > 5:
        result.add(word[:-3])

    if word.endswith("ed") and len(word) > 4:
        result.add(word[:-2])

    return result


def expanded_words(words: set[str]) -> set[str]:
    result = set()

    for word in words:
        result.update(related_words(word))

    return result


# ============================================================
# INTENT ALIASES
# ============================================================

# These aliases help paraphrased questions reach the right
# existing knowledge-base record. They do not replace answers.
INTENT_ALIASES = {
    "What is CareerPro Ministry?": [
        "tell me what careerpro is all about",
        "what is career pro",
        "explain careerpro to me",
        "what does careerpro stand for",
        "what is the careerpro ministry about",
        "tell me about careerpro",
        "what is this ministry about",
    ],
    "What does CareerPro Ministry do?": [
        "what services does careerpro provide",
        "what can careerpro help me with",
        "what does careerpro offer",
        "what are the benefits of careerpro",
        "how can careerpro help me",
    ],
    "Does CareerPro support business owners?": [
        "what type of business support can i get",
        "what business support is available",
        "how can careerpro support my business",
        "what support can i get for my business",
        "does careerpro help entrepreneurs",
        "i own a business what support is available",
        "what help is available for business owners",
    ],
    "What is the CareerPro Enterprise Development Fund?": [
        "tell me about the enterprise fund",
        "what is the enterprise fund",
        "what is careerpro business fund",
        "what is the careerpro business funding initiative",
        "how does the enterprise development fund work",
        "what business funding does careerpro offer",
    ],
    "How much is the CareerPro Enterprise Development Fund?": [
        "how much money is in the fund",
        "what is the total enterprise fund amount",
        "how much funding is available",
        "how much is careerpro giving businesses",
        "what is the fund size",
    ],
    "How much will each business receive?": [
        "how much money can my business get",
        "how much will my business receive",
        "how much can one business get",
        "what is the amount per business",
        "how much is available per business",
    ],
    "Is the ₦2 million a loan?": [
        "is the enterprise fund a loan",
        "do i have to pay the money back",
        "is it a grant or a loan",
        "is careerpro funding repayable",
        "will i need to repay the funding",
    ],
    "When will registration for the Enterprise Development Fund open?": [
        "when can i apply for the enterprise fund",
        "when does business funding registration start",
        "when will the grant application open",
        "when can businesses register for funding",
        "is the enterprise fund application open",
    ],
    "Who is the Enterprise Development Fund for?": [
        "who can apply for the enterprise fund",
        "who is eligible for business funding",
        "can my business apply",
        "what are the requirements for the business grant",
        "which businesses qualify for funding",
    ],
    "What is Enterprise Month 2026?": [
        "tell me about enterprise month",
        "what is happening in november",
        "what is careerpro doing in november",
        "what are the enterprise month activities",
    ],
    "What is the Marketplace Masterclass?": [
        "what masterclasses does careerpro organise",
        "what is the careerpro masterclass",
        "what training sessions are available",
    ],
    "What are Marketplace Mentorship Circles?": [
        "how can i get a mentor",
        "does careerpro offer mentorship",
        "how does the mentorship programme work",
        "can someone mentor me in my career",
    ],
    "I am looking for a job. Can CareerPro help me?": [
        "i need a job",
        "can careerpro help me find work",
        "how can i find a job through careerpro",
        "i am searching for employment",
    ],
}


def build_alias_map():
    result = {}

    by_question = {
        normalize(record["question"]): record["question"]
        for record in QA_RECORDS
    }

    for canonical_question, aliases in INTENT_ALIASES.items():
        actual_question = by_question.get(normalize(canonical_question))

        if not actual_question:
            continue

        for alias in aliases:
            result.setdefault(normalize(alias), actual_question)

    return result


ALIAS_MAP = build_alias_map()


# ============================================================
# MATCHING UTILITIES
# ============================================================

def is_generic_fallback(record: dict) -> bool:
    question = normalize(record["question"])

    return any(
        phrase in question
        for phrase in (
            "question that isnt answered here",
            "question that is not answered here",
            "questions not covered",
            "not answered here",
            "not covered",
        )
    )


def fuzzy_similarity(first: str, second: str) -> float:
    first = normalize(first)
    second = normalize(second)

    if not first or not second:
        return 0.0

    return SequenceMatcher(None, first, second).ratio()


def keyword_similarity(user_question: str, stored_text: str) -> float:
    user_words = useful_words(user_question)
    stored_words = useful_words(stored_text)

    if not user_words or not stored_words:
        return 0.0

    user_expanded = expanded_words(user_words)
    stored_expanded = expanded_words(stored_words)

    overlap = user_expanded & stored_expanded

    user_coverage = len(overlap) / max(len(user_expanded), 1)
    stored_coverage = len(overlap) / max(len(stored_expanded), 1)

    # Favour covering the user's intent, while still rewarding
    # matches that describe the stored question accurately.
    return 0.7 * user_coverage + 0.3 * stored_coverage


def phrase_bonus(user_question: str, stored_text: str) -> float:
    user_text = normalize(user_question)
    stored_text = normalize(stored_text)

    if not user_text or not stored_text:
        return 0.0

    if user_text == stored_text:
        return 1.0

    if len(user_text) >= 5 and user_text in stored_text:
        return 0.7

    if len(stored_text) >= 5 and stored_text in user_text:
        return 0.65

    return 0.0


def answer_topic_score(user_question: str, answer: str) -> float:
    """
    Use answer content as supporting evidence.

    This helps when the user mentions a term that appears in the
    answer but not in the original stored question.
    """
    question_words = useful_words(user_question)
    answer_words = useful_words(answer)

    if not question_words or not answer_words:
        return 0.0

    expanded_question = expanded_words(question_words)
    expanded_answer = expanded_words(answer_words)

    overlap = expanded_question & expanded_answer

    return len(overlap) / max(len(expanded_question), 1)


def record_score(user_question: str, record: dict) -> float:
    user_text = normalize(user_question)
    stored_question = record["question"]
    stored_answer = record["answer"]

    if user_text == normalize(stored_question):
        return 1.0

    fuzzy_score = fuzzy_similarity(user_text, stored_question)
    keyword_score = keyword_similarity(user_question, stored_question)
    phrase_score = phrase_bonus(user_question, stored_question)
    answer_score = answer_topic_score(user_question, stored_answer)

    score = (
        fuzzy_score * 0.20
        + keyword_score * 0.50
        + phrase_score * 0.10
        + answer_score * 0.20
    )

    # Specific, meaningful query terms should overlap with the
    # stored question or answer. Avoid fuzzy-only false positives.
    user_words = useful_words(user_question)
    stored_words = useful_words(stored_question)
    answer_words = useful_words(stored_answer)

    expanded_user = expanded_words(user_words)
    expanded_question = expanded_words(stored_words)
    expanded_answer = expanded_words(answer_words)

    if not (
        expanded_user.intersection(expanded_question)
        or expanded_user.intersection(expanded_answer)
    ):
        return 0.0

    return min(score, 1.0)


# ============================================================
# TOPIC ROUTING
# ============================================================

TOPIC_HINTS = {
    "enterprise_fund": {
        "enterprise fund", "development fund", "business grant",
        "business funding", "funding cycle", "two million",
        "2 million", "₦2 million", "grant application",
    },
    "business_support": {
        "business support", "support my business",
        "business owner", "business owners", "entrepreneur",
        "entrepreneurship",
    },
    "careerpro_about": {
        "what is careerpro", "about careerpro",
        "careerpro ministry", "careerpro all about",
    },
    "enterprise_month": {
        "enterprise month", "november activities",
        "november programme",
    },
}


def detect_topic(question: str):
    text = normalize(question)

    # Check the more specific funding topic first.
    if any(
        normalize(hint) in text
        for hint in TOPIC_HINTS["enterprise_fund"]
    ):
        return "enterprise_fund"

    if any(
        normalize(hint) in text
        for hint in TOPIC_HINTS["business_support"]
    ):
        return "business_support"

    if any(
        normalize(hint) in text
        for hint in TOPIC_HINTS["careerpro_about"]
    ):
        return "careerpro_about"

    if any(
        normalize(hint) in text
        for hint in TOPIC_HINTS["enterprise_month"]
    ):
        return "enterprise_month"

    return None


def topic_priority(question: str, record: dict) -> float:
    topic = detect_topic(question)
    stored_question = normalize(record["question"])
    stored_answer = normalize(record["answer"])

    if not topic:
        return 0.0

    if topic == "enterprise_fund":
        if any(term in stored_question for term in (
            "enterprise development fund",
            "how much is the careerpro enterprise",
            "how many businesses will receive funding",
            "how much will each business receive",
            "is the 2 million a loan",
            "when will registration for the enterprise",
            "who is the enterprise development fund for",
        )):
            return 0.16

        if "enterprise development fund" in stored_answer:
            return 0.05

    elif topic == "business_support":
        if "does careerpro support business owners" in stored_question:
            return 0.15

        if "business and entrepreneurship support" in stored_question:
            return 0.12

        if "enterprise development fund" in stored_question:
            return 0.08

    elif topic == "careerpro_about":
        if stored_question == "what is careerpro ministry":
            return 0.18

    elif topic == "enterprise_month":
        if "enterprise month 2026" in stored_question:
            return 0.15

    return 0.0


# ============================================================
# RETRIEVE THE BEST MATCH
# ============================================================

def retrieve_best_match(user_question: str):
    if not QA_RECORDS:
        return None

    user_text = normalize(user_question)
    user_words = useful_words(user_question)

    if not user_words:
        return None

    # Explicit alias match is the strongest paraphrase signal.
    alias_question = ALIAS_MAP.get(user_text)

    if alias_question:
        for record in QA_RECORDS:
            if normalize(record["question"]) == normalize(alias_question):
                return {
                    "record": record,
                    "score": 0.96,
                    "method": "alias",
                }

    candidates = []

    for record in QA_RECORDS:
        if is_generic_fallback(record):
            continue

        score = record_score(user_question, record)
        score += topic_priority(user_question, record)
        score = min(score, 1.0)

        candidates.append({
            "record": record,
            "score": score,
            "method": "hybrid",
        })

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    best = candidates[0]

    # Conservative threshold: avoid confident answers to unrelated
    # questions when the knowledge base does not contain the answer.
    if best["score"] < 0.34:
        return None

    if len(candidates) > 1:
        second = candidates[1]

        # If the best two results are nearly tied, require stronger
        # evidence rather than returning a potentially unrelated answer.
        if (
            best["score"] < 0.48
            and best["score"] - second["score"] < 0.035
        ):
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
