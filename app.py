import hashlib
import hmac
import json
import os
import re

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from job_sources import is_verified, search_jobs

load_dotenv()

app = FastAPI(title="The Elevation Church Ogba CareerPro Ministry Chatbot")

VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
WA_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
PHONE_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")
API_VERSION = os.getenv("GRAPH_API_VERSION", "")


@app.get("/")
async def home():
    return FileResponse("index.html")

@app.get("/health")
async def health():
    return {"status": "ok", "service": "careerpro-ministry-chatbot"}


@app.get("/api/search")
async def web_search(q: str):
    query = re.sub(r"\s+", " ", q).strip()
    if len(query) < 3:
        raise HTTPException(status_code=400, detail="Please enter a job title or search request.")

    # Only verified listings are shown as verified.
    jobs = [job for job in search_jobs(query) if is_verified(job)]
    return {
        "query": query,
        "results": [
            {
                "title": j.title,
                "company": j.company,
                "location": j.location,
                "work_mode": j.work_mode,
                "source": j.source,
                "source_url": j.source_url,
                "apply_url": j.apply_url,
                "posted_at": j.posted_at,
                "closing_at": j.closing_at,
                "verification": "Verified"
            }
            for j in jobs[:10]
        ],
        "message": None if jobs else (
            "No vacancies are connected to this prototype yet. "
            "An authorised live job source must be connected before it can return real vacancies."
        )
    }


@app.get("/webhook")
async def verify_webhook(request: Request):
    p = request.query_params
    if (
        p.get("hub.mode") == "subscribe"
        and VERIFY_TOKEN
        and hmac.compare_digest(p.get("hub.verify_token", ""), VERIFY_TOKEN)
        and p.get("hub.challenge", "").isdigit()
    ):
        return int(p["hub.challenge"])
    raise HTTPException(status_code=403, detail="Webhook verification failed")


async def send_whatsapp(to: str, message: str):
    if not all([WA_TOKEN, PHONE_ID, API_VERSION]):
        raise RuntimeError("WhatsApp credentials are not configured.")
    url = f"https://graph.facebook.com/{API_VERSION}/{PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WA_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": True, "body": message[:4000]},
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()


def format_results(query: str) -> str:
    jobs = [job for job in search_jobs(query) if is_verified(job)]
    if not jobs:
        return (
            "The Elevation Church Ogba CareerPro Ministry Chatbot\n\n"
            "I couldn't find a vacancy that this service can currently confirm as verified. "
            "The live job-source connection may not yet be configured. I won't invent job listings.\n\n"
            "Try a broader job title, or check an employer's official careers page."
        )
    lines = ["The Elevation Church Ogba CareerPro Ministry Chatbot\n"]
    for i, j in enumerate(jobs[:5], 1):
        lines.append(
            f"{i}. {j.title}\nCompany: {j.company}\nLocation: {j.location}\n"
            f"Work mode: {j.work_mode}\nSource: {j.source}\n"
            f"Posted: {j.posted_at or 'Not stated'}\nApply: {j.apply_url}\n"
        )
    lines.append("Safety tip: never pay a recruiter to apply for a job.")
    return "\n".join(lines)


def verify_meta_signature(raw_body: bytes, signature_header: str | None) -> bool:
    # Meta signs webhook payloads with the app secret. Configure this
    # secret before production; never disable signature validation publicly.
    if not APP_SECRET or not signature_header:
        return False
    expected = "sha256=" + hmac.new(
        APP_SECRET.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


@app.post("/webhook")
async def receive_webhook(request: Request):
    raw = await request.body()
    if not verify_meta_signature(raw, request.headers.get("x-hub-signature-256")):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Ignore status events; reply to inbound text messages only.
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []):
                if msg.get("type") != "text":
                    continue
                sender = msg.get("from", "")
                incoming = msg.get("text", {}).get("body", "").strip()
                if not sender or not incoming:
                    continue

                if incoming.lower() in {"hi", "hello", "menu", "start"}:
                    reply = (
                        "Welcome to The Elevation Church Ogba CareerPro Ministry Chatbot!\n\n"
                        "Tell me the job you want, your experience, location, industry "
                        "and preferred work mode.\n\n"
                        "Example: Data Governance Manager, 15 years, Lagos, fintech, hybrid."
                    )
                else:
                    reply = format_results(incoming)
                try:
                    await send_whatsapp(sender, reply)
                except Exception:
                    # In production, log a safe error and retry via a queue.
                    # Do not log access tokens or full personal message contents.
                    return JSONResponse({"status": "send_failed"}, status_code=500)

    return {"status": "ok"}
